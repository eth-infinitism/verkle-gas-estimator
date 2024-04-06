#!/usr/bin/env python3
import subprocess
import sys
import os
import re


# Function to run cast command and return output
def run_cast(command):
    return subprocess.check_output(command, shell=True, text=True)


dumpall = False
debug = os.environ.get("DEBUG") is not None
cast_executable = "/Users/dror/Downloads/aa/foundry/target/release/cast"


def usage():
    print(f"usage: {sys.argv[0]} [options] {{tx|file}} [-r network]")
    print("count storage 'slots' (blocks of 31 bytes) of each contract in a transaction.")
    print("Options:")
    print("  -a dump all slots, not only count/max")
    print("  -c {cast-path} use specified 'cast' implementation ")
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
slots = {}

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
            slot = pc // 31
            if addr not in slots:
                slots[addr] = {}
            slots[addr][slot] = slots[addr].get(slot, 0) + 1
            if debug:
                print(f"{addr}, {slot}, {pc}, {opcode}")
            lastdepth = depth

print("verkle slots used by each address (slot=pc//31)")
# Dump number of unique slots used by each address
for addr in slots:
    max_slot = max(slots[addr].keys())
    num_slots = len(slots[addr])
    if dumpall:
        print(f"{addr} {num_slots} (max= {max_slot}), all={','.join(map(str, slots[addr].keys()))}")
    else:
        print(f"{addr} {num_slots} (max= {max_slot})")
