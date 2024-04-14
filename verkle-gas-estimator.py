#!/usr/bin/env python3
import json
import math
import os
import re
import subprocess
import sys


# Function to run cast command and return output
def run_cast(command):
    cmd = f"{cast_executable} {command}"
    return subprocess.check_output(cmd, shell=True, text=True)


names = {}
test_cases = []


def get_name(address):
    if address not in names or names[address] is None:
        return address
    else:
        shortAddress = "(" + address[:8] + "..." + address[38:] + ")"
        return names[address] + " " + shortAddress


HEADER_STORAGE_OFFSET = 64
CODE_OFFSET = 128
VERKLE_NODE_WIDTH = 256
MAIN_STORAGE_OFFSET = 256 ** 31

WITNESS_BRANCH_COST = 1900
WITNESS_CHUNK_COST = 200

COLD_SLOAD_COST = 2100
COLD_ACCOUNT_ACCESS_COST = 2600

SUBTREE_EDIT_COST = 3000
CHUNK_EDIT_COST = 500
CHUNK_FILL_COST = 6200


def calculate_deployment_gas_effect(contract_size):
    code_chunks = contract_size // 31
    code_subtrees = math.ceil((code_chunks + CODE_OFFSET) / 256)
    return CHUNK_FILL_COST * code_chunks + SUBTREE_EDIT_COST * code_subtrees


def calculate_gas_effect(contract_chunks, contract_slots):
    code_cost = 0
    # code_cost -= COLD_ACCOUNT_ACCESS_COST  # uncomment if Verkle replaces EIP-2929 warm/cold gas pricing
    storage_cost = 0
    branches_access_events = {0: True}  # consider "main code" cost to be free
    for [contract_chunk, _] in contract_chunks.items():
        code_cost += WITNESS_CHUNK_COST
        branch_id = contract_chunk // 256
        if branch_id not in branches_access_events:
            branches_access_events[branch_id] = True
            code_cost += WITNESS_BRANCH_COST

    for [storage_key_hex, _] in contract_slots.items():
        # storage_cost -= COLD_SLOAD_COST  # uncomment if Verkle replaces EIP-2929 warm/cold gas pricing
        storage_cost += WITNESS_CHUNK_COST
        storage_key = int(storage_key_hex, 16)
        # special storage for slots 0..64
        if storage_key < (CODE_OFFSET - HEADER_STORAGE_OFFSET):
            pos = HEADER_STORAGE_OFFSET + storage_key
        else:
            pos = MAIN_STORAGE_OFFSET + storage_key
        branch_id = pos // VERKLE_NODE_WIDTH
        if branch_id not in branches_access_events:
            branches_access_events[branch_id] = True
            storage_cost += WITNESS_BRANCH_COST

    return [code_cost, storage_cost]


def evaluate_test_case(case):
    print("********")
    print(case['name'])
    print(case['txHash'])
    print(case['userOpsCount'])
    print(case['totalGasUsed'])
    print("********")


dumpall = False
debug = os.environ.get("DEBUG") is not None
extraDebug = False
cast_executable = "cast"


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
        test_cases = json.load(f)
    else:
        raise Exception("Unknown option " + opt)

# Check if file exists, read file instead of running cast run
if len(args) > 0 and os.path.exists(args[0]):
    with open(args[0], 'r') as f:
        output = f.read()

elif len(test_cases) > 0:
    for test_case in test_cases:
        evaluate_test_case(test_case)
else:
    argStr = " ".join(args)
    output = run_cast(f"run -t --quick {argStr}")

addrs = []
lastdepth = 0
chunks = {}
slots = {}

line = None
lastGas = None
lastRefund = None

lines = output.splitlines()
for lineNumber in range(len(lines)):
    line = lines[lineNumber]
    if "Traces:" in line:
        break
    if "CREATE CALL:" in line:
        continue
    if "SM CALL" in line:
        (sm_context_address, sm_code_address) = re.search("address: (\w+).*code_address: (\w+)", line).groups()
        continue

    if "depth:" in line:

        # depth:1, PC:0, gas:0x10c631(1099313), OPCODE: "PUSH1"(96)  refund:0x0(0) Stack:[], Data size:0, Data: 0x
        (depth, pc, lineGas, opcode, lineRefund, stackStr) = re.search(
            "depth:(\d+).*PC:(\d+).*gas:\w+\((\w+)\).*OPCODE: \"(\w+)\".*refund:\w+\((\w+)\).*Stack:\[(.*)\]",
            line).groups()

        gas = None
        refund = None
        # cannot check *CALL: next opcode is in different context
        if "depth:" in lines[lineNumber + 1]:
            (nextGas, nextRefund, nextStackStr) = re.search(
                "gas:\w+\((\w+)\).*refund:\w+\((\w+)\).*Stack:\[(.*)\]",
                lines[lineNumber + 1]).groups()

            # gas, refund by this opcode
            gas = int(lineGas) - int(nextGas)
            refund = int(nextRefund) - int(lineRefund)

        stack = stackStr.replace("_U256", "").split(", ")[-2:]
        if opcode == "SSTORE":
            (val, storageSlot) = stack
            if context_address not in slots:
                slots[context_address] = {}
            slots[context_address][storageSlot] = True
            if debug: print(
                f"{opcode} context={context_address} slot={storageSlot} gas={gas} refund={refund} val={val}")
        if opcode == "SLOAD":
            (storageSlot,) = stack[-1:]
            if context_address not in slots:
                slots[context_address] = {}
            slots[context_address][storageSlot] = True
            nextStack = nextStackStr.replace("_U256", "").split(", ")[-2:]
            if debug: print(
                f"{opcode} context={context_address} slot={storageSlot} gas={gas} refund={refund}, ret={nextStack[-1:][0]}")
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

print("Verkle chunks used by each address (slot=pc//31)")
print("")

total_gas_effect = 0
# Dump number of unique slots used by each address
for addr in chunks:
    max_chunk = max(chunks[addr].keys())
    num_chunks = len(chunks[addr])

    name = get_name(addr)
    addr_slots = {}
    if addr in slots:
        addr_slots = slots[addr]
    [addr_code_cost, addr_storage_cost] = calculate_gas_effect(chunks[addr], addr_slots)
    total_gas_effect += addr_code_cost
    total_gas_effect += addr_storage_cost
    code_size = 0
    try:
        code_size = int(run_cast(f"codesize {addr} 2>/dev/null").strip())
    except:
        pass
    code_size_chunks = (code_size + 30) // 31
    max_chunk = max(chunks[addr].keys())
    dumpallSuffix = ""
    if dumpall:
        dumpallSuffix = f", all={','.join(map(str, chunks[addr].keys()))}"
    if code_size > 0:
        codeInfo = f"bytes:{code_size} chunks:{code_size_chunks} max:{max_chunk}"
    else:
        codeInfo = f"max_chunk:{max_chunk}"
    print(
        f"{name} code:({codeInfo} accessed-chunks:{num_chunks}) storage-slots:{len(addr_slots)} [verkle: code={addr_code_cost} + storage={addr_storage_cost}]{dumpallSuffix}")

print("")
print("Total Verkle gas effect = " + str(total_gas_effect))
