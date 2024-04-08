#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys


# Function to run cast command and return output
def run_cast(command):
    cmd=f"{cast_executable} {command}"
    return subprocess.check_output(cmd, shell=True, text=True)


names = {}


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


dumpall = False
debug = os.environ.get("DEBUG") is not None
cast_executable = "cast"


def usage():
    print(f"usage: {sys.argv[0]} [options] {{tx|file}} [-r network]")
    print("count storage 'chunks' (blocks of 31 bytes) of each contract in a transaction.")
    print("Options:")
    print("  -a dump all chunks, not only count/max")
    print("  -c {cast-path} use specified 'cast' implementation ")
    print("  -contracts match contract addresses with names in given JSON file")
    print("Parameters:")
    print("  tx - tx to read. It (and all following params) are passed directly into `cast run -t --quick`")
    print("  file - if the first param is an existing file, it is read instead.")
    print("         The file should be the output of `cast run -t --quick {tx} > FILE`")
    sys.exit(1)


args = sys.argv[1:]
if args == []:
    args = ["-h"]

while re.match("^-", args[0]):
    opt = args.pop(0)
    if opt == "-h":
        usage()
    elif opt == "-c":
        cast_executable = args.pop(0)
    elif opt == "-a":
        dumpall = True
    elif opt == "-d":
        debug = True
    elif opt == "-contracts":
        f = open(args.pop(0))
        file = json.load(f)
        names = file["contracts"]
    else:
        raise Exception("Unknown option " + opt)

# Check if file exists, read file instead of running cast run
if os.path.exists(args[0]):
    with open(args[0], 'r') as f:
        output = f.read()
else:
    argStr = " ".join(args)
    output = run_cast(f"run -t --quick {argStr}")

addrs = []
lastdepth = 0
chunks = {}
slots = {}

for line in output.splitlines():
    if "Traces:" in line:
        break
    if "CREATE CALL:" in line:
        continue
    if "SM CALL" in line:
        (sm_context_address, sm_code_address) = re.search("address: (\w+).*code_address: (\w+)", line).groups()
        continue
    if "depth:" in line:
        #    ( $depth, $pc, $opcode ) = /depth:(\d+).*PC:(\d+),.*OPCODE: "(\w+)"/;

        (depth, pc, opcode, stackStr) = re.search("depth:(\d+).*PC:(\d+).*OPCODE: \"(\w+)\".*Stack:\[(.*)\]",
                                                  line).groups()
        stack = stackStr.replace("_U256", "").split(", ")
        if opcode == "SSTORE":
            (val, storageSlot) = stack[-2:]
            if context_address not in slots:
                slots[context_address] = {}
            slots[context_address][storageSlot] = True
            if debug: print(f"{opcode} context={context_address} slot={storageSlot} val={val}")
        if opcode == "SLOAD":
            (storageSlot,) = stack[-1:]
            if context_address not in slots:
                slots[context_address] = {}
            slots[context_address][storageSlot] = True
            if debug: print(f"{opcode} context={context_address} slot={storageSlot}")
        if depth:
            depth = int(depth)
            if depth == lastdepth + 1:
                addrs.append( (sm_code_address, sm_context_address) )
                (addr, context_address) = addrs[-1]
            if depth == lastdepth - 1:
                addrs.pop()
                (addr, context_address) = addrs[-1]
            pc = int(pc)
            chunk = pc // 31
            if addr not in chunks:
                chunks[addr] = {}
            chunks[addr][chunk] = chunks[addr].get(chunk, 0) + 1
            # if debug:
            #     print(f"{addr}, {chunk}, {pc}, {opcode}, {stack[-2:]}")
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
    code_size = run_cast(f"codesize {addr}").strip()
    code_size_chunks = (int(code_size)+30)//31
    dumpallSuffix=""
    if dumpall:
        dumpallSuffix=", all={','.join(map(str, chunks[addr].keys()))}"
    print(
        f"{name} code:(size:{code_size}/{code_size_chunks} accessed-chunks:{num_chunks}) storage-slots:{len(addr_slots)} [verkle: code={addr_code_cost} + storage={addr_storage_cost}]"+dumpallSuffix)

print("")
print("Total Verkle gas effect = " + str(total_gas_effect))
