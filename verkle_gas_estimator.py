#!/usr/bin/env python3
import csv
import json
import os
import re
import subprocess
import sys

from estimation import estimate_verkle_gas_cost_difference
from print_results import print_results


# Function to run cast command and return output
def run_cast(command):
    cmd = f"{cast_executable} {command}"
    return subprocess.check_output(cmd, shell=True, text=True).strip()


names = {}
test_cases = []

dumpall = False
debug = os.environ.get("DEBUG") is not None
extraDebug = False
__dir__ = os.path.dirname(os.path.realpath(__file__))
# make sure to use "cast" from an empty folder. it runs VERY slow if there are sub-folders...
cast_executable = __dir__ + "/fastcast"
# call_opcodes=["CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"]
ADDRESS_TOUCHING_OPCODES = ["EXTCODESIZE", "EXTCODECOPY", "EXTCODEHASH", "BALANCE", "SELFDESTRUCT"]


def usage():
    print(f"usage: {sys.argv[0]} [options] {{tx|file}} [-r network]")
    print("count storage 'chunks' (blocks of 31 bytes) of each contract in a transaction.")
    print("Options:")
    print("  -a dump all chunks, not only count/max")
    print("  -c {cast-path} use specified 'cast' implementation ")
    print("  -contracts match contract addresses with names in given JSON file")
    print("  -multiple iterate over transactions in a JSON results file and calculate results for each entry")
    print("Parameters:")
    print("  tx - tx to read. It (and all following params) are passed directly into `cast run -t --quick`")
    print("  file - if the first param is an existing file, it is read instead.")
    print("         The file should be the output of `cast run -t --quick {tx} > FILE`")
    sys.exit(1)


args = sys.argv[1:]
if args == []:
    args = ["-h"]

while len(args) > 0 and re.match("^-", args[0]):
    opt = args.pop(0)
    if opt == "-h":
        usage()
    elif opt == "-c":
        cast_executable = args.pop(0)
    elif opt == "-a":
        dumpall = True
    elif opt == "-d":
        debug = True
    elif opt == "-dd":
        extraDebug = True
    elif opt == "-contracts":
        f = open(args.pop(0))
        file = json.load(f)
        names = file["contracts"]
    elif opt == "-multiple":
        f = open(args.pop(0))
        multiple_results = json.load(f)
        test_cases = multiple_results['results']
        names = multiple_results['contracts']
    else:
        raise Exception("Unknown option " + opt)


def parse_trace_results(case, output):
    print(f"Evaluating transaction {case['txHash']}")

    addrs = []
    lastdepth = 0
    chunks = {}
    slots = {}
    touched = {}
    code_sizes = {}
    count_call_with_value = {}
    created_contracts = {}

    # line = None
    # lastGas = None
    # lastRefund = None

    lines = output.splitlines()
    for lineNumber in range(len(lines)):
        line = lines[lineNumber]
        if "Traces:" in line:
            break
        if "CREATE CALL:" in line:
            # CREATE CALL: caller:0x5de4839a76cf55d0c90e2061ef4386d962E15ae3, scheme:Create2 { salt: 0x0000000000000000000000000000000000000000114ea8212b2f9f4cb29398d9_U256

            (caller, salt, initcode) = re.search(
                r"caller:(\w+).*salt: (\w+)_U256.* init_code:\"(\w+)\"",
                line).groups()

            res = run_cast(f"keccak `cast concat-hex 0xff {caller} {salt} \\`cast keccak 0x{initcode}\\` `")
            # res is 32-byte. need to take last 20
            created_address = "0x" + res[26:]
            created_address = created_address.lower()
            caller = caller.lower()
            if caller not in created_contracts:
                created_contracts[caller] = []
            created_contracts[caller].append(created_address)
            continue
        if "SM CALL" in line:
            # SM CALL:   0x7fc..,context:CallContext { address: 0x7fc, caller: 0x5ff, code_address: 0x7fc, apparent_value: 0x0_U256, scheme: Call }, is_static:false, transfer:Transfer { source: 0x5ff137d4b0fdcd49dca30c7cf57e578a026d2789, target:
            # 0x7fc98430eaedbb6070b35b39d798725049088348, value: 0x0_U256 }, input_size:388
            (sm_context_address, sm_code_address, scheme, sm_value) = re.search(
                r"address: (\w+).*code_address: (\w+).*scheme: (\w+).* value: (\w+)_U256",
                line).groups()
            if debug: print(f"Call {scheme} code-address: {sm_code_address}")
            sm_context_address = sm_context_address.lower()
            if int(sm_value, 16) != 0:
                if sm_context_address not in count_call_with_value:
                    count_call_with_value[sm_context_address] = 0
                count_call_with_value[sm_context_address] += 1
            continue

        if "depth:" in line:

            # depth:1, PC:0, gas:0x10c631(1099313), OPCODE: "PUSH1"(96)  refund:0x0(0) Stack:[], Data size:0, Data: 0x
            (depth, pc, lineGas, opcode, lineRefund, stackStr) = re.search(
                r"depth:(\d+).*PC:(\d+).*gas:\w+\((\w+)\).*OPCODE: \"(\w+)\".*refund:\w+\((\w+)\).*Stack:\[(.*)\]",
                line).groups()

            gas = None
            refund = None
            # cannot check *CALL: next opcode is in different context
            if "depth:" in lines[lineNumber + 1]:
                (nextGas, nextRefund, next_stack_str) = re.search(
                    r"gas:\w+\((\w+)\).*refund:\w+\((\w+)\).*Stack:\[(.*)\]",
                    lines[lineNumber + 1]).groups()

                # gas, refund by this opcode
                gas = int(lineGas) - int(nextGas)
                refund = int(nextRefund) - int(lineRefund)

            stack = stackStr.replace("_U256", "").split(", ")[-2:]

            if opcode in ADDRESS_TOUCHING_OPCODES:
                touched_address = stack[-1]
                touched_address = f"0x{touched_address[26:]}"
                touched[touched_address.lower()] = True
                # add address to the list of touched addresses
                # (note: in normal case, these opcodes are used in conjuction of "call" opcodes, but
                # a code may call (say) EXTCODESIZE without making a call

            if opcode == "SSTORE":
                (val, storage_slot) = stack
                context_address = context_address.lower()
                if context_address not in slots:
                    slots[context_address] = {}
                if storage_slot not in slots[context_address]:
                    slots[context_address][storage_slot] = []

                slots[context_address][storage_slot].append({
                    'opcode': opcode,
                    'gas': gas,
                    'refund': refund
                })
                if debug: print(
                    f"{opcode} context={context_address} slot={storage_slot} gas={gas} refund={refund} val={val}")
            if opcode == "SLOAD":
                (storage_slot,) = stack[-1:]
                context_address = context_address.lower()
                if context_address not in slots:
                    slots[context_address] = {}
                if storage_slot not in slots[context_address]:
                    slots[context_address][storage_slot] = []
                slots[context_address][storage_slot].append({
                    'opcode': opcode,
                    'gas': gas,
                    'refund': refund
                })
                next_stack = next_stack_str.replace("_U256", "").split(", ")[-2:]
                if debug: print(
                    f"{opcode} context={context_address} slot={storage_slot} gas={gas} refund={refund}, ret={next_stack[-1:][0]}")
            if depth:
                depth = int(depth)
                if depth == lastdepth + 1:
                    addrs.append((sm_code_address, sm_context_address))
                    (addr, context_address) = addrs[-1]
                if depth == lastdepth - 1:
                    addrs.pop()
                    (addr, context_address) = addrs[-1]
                pc = int(pc)
                chunk = pc // 31
                addr = addr.lower()
                if addr not in chunks:
                    chunks[addr] = {}
                chunks[addr][chunk] = chunks[addr].get(chunk, 0) + 1
                if extraDebug:
                    print(f"{addr}, {chunk}, {pc}, {opcode}, {gas}, {stack}")
                lastdepth = depth

    for address in chunks:
        code_sizes[address] = -1
        try:
            code_sizes[address] = int(run_cast(f"codesize {address} 2>/dev/null"))
        except:
            pass

    return dict(
        code_sizes=code_sizes,
        chunks=chunks,
        slots=slots,
        touched=touched,
        count_call_with_value=count_call_with_value,
        created_contracts=created_contracts
    )


def evaluate_test_case(case):
    output = run_cast(f"run -t --quick {case['txHash']}")
    trace_results = parse_trace_results(case, output)
    verkle_results = estimate_verkle_gas_cost_difference(trace_results, names)
    print_results(case['name'], case['totalGasUsed'], verkle_results, dumpall)
    pre_verkle_gas_used = case.get('totalGasUsed')
    gasUsed = int(re.search(r"Gas used: (\d+)", output).groups(0)[0])
    if pre_verkle_gas_used is None:
        pre_verkle_gas_used = gasUsed
    assert gasUsed == pre_verkle_gas_used
    post_verkle_gas_used = pre_verkle_gas_used + verkle_results['total_gas_cost_difference']
    return [case['name'], pre_verkle_gas_used, post_verkle_gas_used]


def write_csv(rows):
    with open('verkle-effects-estimate.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["name", "pre_verkle_gas_used", "post_verkle_gas_used", "marginal_pre_verkle", "marginal_post_verkle"])
        for row in rows:
            writer.writerow(row)


# Check if file exists, read file instead of running cast run
if len(args) > 0 and os.path.exists(args[0]):
    with open(args[0], 'r') as f:
        cast_output = f.read()
        estimate_verkle_gas_cost_difference(cast_output, names)
elif len(test_cases) > 0:
    evaluated = []
    lastpre = 0
    lastpost = 0
    for test_case in test_cases:
        row = evaluate_test_case(test_case)
        if "double" in row[0]:
            row.append(row[1]-lastpre)
            row.append(row[2]-lastpost)
        else:
            lastpre = row[1]
            lastpost = row[2]
        evaluated.append(row)
    write_csv(evaluated)
else:
    argStr = " ".join(args)
    # cast_output = run_cast(f"run -t --quick {argStr}")
    # estimate_verkle_effect(cast_output, names)
    evaluate_test_case(dict(
        txHash=argStr,
        name='cmdline'
    ))

