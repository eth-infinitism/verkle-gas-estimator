#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys


# Function to run cast command and return output
def run_cast(command):
    return subprocess.check_output(command, shell=True, text=True)


names = {}


def get_name(address):
    if address not in names or names[address] is None:
        return address
    else:
        shortAddress = "(" + address[:8] + "..." + address[38:] + ")"
        return names[address] + " " + shortAddress


def calculate_gas_effect(contract_chunks, contract_slots):
    cost = 0
    branches_access_events = {0: True}  # consider "main code" cost to be free
    for [contract_chunk, _] in contract_chunks.items():
        cost += 200  # cost per chunk
        branch_id = contract_chunk // 256
        if branch_id not in branches_access_events:
            branches_access_events[branch_id] = True
            cost += 1900  # cost per branch
    return cost

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
    output = run_cast(f"{cast_executable} run -t --quick {argStr}")

addrs = []
lastdepth = 0
chunks = {}

for line in output.splitlines():
    if "Traces:" in line:
        break
    if "CREATE CALL:" in line:
        continue
    if "SM CALL" in line:
        (code_address,) = re.search("code_address: (\w+)", line).groups()
        continue
    if "depth:" in line:
        #    ( $depth, $pc, $opcode ) = /depth:(\d+).*PC:(\d+),.*OPCODE: "(\w+)"/;

        (depth, pc, opcode) = re.search("depth:(\d+).*PC:(\d+).*OPCODE: \"(\w+)\"", line).groups()
        if depth:
            depth = int(depth)
            if depth == lastdepth + 1:
                addrs.append(code_address)
                addr = addrs[-1]
            if depth == lastdepth - 1:
                addrs.pop()
                addr = addrs[-1]
            pc = int(pc)
            chunk = pc // 31
            if addr not in chunks:
                chunks[addr] = {}
            chunks[addr][chunk] = chunks[addr].get(chunk, 0) + 1
            if debug:
                print(f"{addr}, {chunk}, {pc}, {opcode}")
            lastdepth = depth

print("Verkle chunks used by each address (slot=pc//31)")
print("")

total_gas_effect = 0
# Dump number of unique slots used by each address
for addr in chunks:
    max_chunk = max(chunks[addr].keys())
    num_chunks = len(chunks[addr])

    name = get_name(addr)
    gas_effect = calculate_gas_effect(chunks[addr], [])
    total_gas_effect += gas_effect

    if dumpall:
        print(f"{name} {num_chunks} (max= {max_chunk}) [gas_effect= {gas_effect}], all={','.join(map(str, chunks[addr].keys()))}")
    else:
        print(f"{name} {num_chunks} (max= {max_chunk}) [gas_effect= {gas_effect}]")

print("")
print("Total Verkle code chunks gas effect = " + str(total_gas_effect))

