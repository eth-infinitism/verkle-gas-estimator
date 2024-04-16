#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys

from estimation import estimate_verkle_effect
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
cast_executable = "cast"
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
    code_sizes = {}
    count_call_with_value = 0
    created_contracts = []

    # line = None
    # lastGas = None
    # lastRefund = None

    lines = output.splitlines()
    for lineNumber in range(len(lines)):
        line = lines[lineNumber]
        if "Traces:" in line:
            break
        if "CREATE CALL:" in line:
            #CREATE CALL: caller:0x5de4839a76cf55d0c90e2061ef4386d962E15ae3, scheme:Create2 { salt: 0x0000000000000000000000000000000000000000114ea8212b2f9f4cb29398d9_U256

            (caller, salt, initcode) = re.search(
                r"caller:(\w+).*salt: (\w+)_U256.* init_code:\"(\w+)\"",
                line).groups()

            res = run_cast(f"keccak `cast concat-hex 0xff {caller} {salt} \\`cast keccak 0x{initcode}\\` `")
            # res is 32-byte. need to take last 20
            addr = "0x" + res[26:]
            created_contracts.append(addr)
            continue
        if "SM CALL" in line:
            #SM CALL:   0x7fc..,context:CallContext { address: 0x7fc, caller: 0x5ff, code_address: 0x7fc, apparent_value: 0x0_U256, scheme: Call }, is_static:false, transfer:Transfer { source: 0x5ff137d4b0fdcd49dca30c7cf57e578a026d2789, target:
            # 0x7fc98430eaedbb6070b35b39d798725049088348, value: 0x0_U256 }, input_size:388
            (sm_context_address, sm_code_address, sm_value) = re.search(
                r"address: (\w+).*code_address: (\w+).* value: (\w+)_U256",
                line).groups()
            if sm_value != "0":
                count_call_with_value += 1
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
                addr = stack[-1]
                slots[addr] = {}
                #add address to the list of touched addresses
                #(note: in normal case, these opcodes are used in conjuction of "call" opcodes, but
                # a code may call (say) EXTCODESIZE without making a call

            if opcode == "SSTORE":
                (val, storage_slot) = stack
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
        count_call_with_value=count_call_with_value,
        created_contracts=created_contracts
    )


def evaluate_test_case(case):
    output = run_cast(f"run -t --quick {case['txHash']}")
    trace_results = parse_trace_results(case, output)
    verkle_results = estimate_verkle_effect(trace_results, names)
    print_results(verkle_results, dumpall)


# Check if file exists, read file instead of running cast run
if len(args) > 0 and os.path.exists(args[0]):
    with open(args[0], 'r') as f:
        cast_output = f.read()
        estimate_verkle_effect(cast_output, names)
elif len(test_cases) > 0:
    for test_case in test_cases:
        evaluate_test_case(test_case)
else:
    argStr = " ".join(args)
    cast_output = run_cast(f"run -t --quick {argStr}")
    estimate_verkle_effect(cast_output, names)
