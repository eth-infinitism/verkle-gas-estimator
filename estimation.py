import math

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


def calculate_chunks_read_verkle_effect(contract_chunks, branches_access_events):
    code_cost = 0
    for [contract_chunk, _] in contract_chunks.items():
        code_cost += WITNESS_CHUNK_COST
        branch_id = contract_chunk // 256
        if branch_id not in branches_access_events:
            branches_access_events[branch_id] = True
            code_cost += WITNESS_BRANCH_COST
    return code_cost


def calculate_slots_read_verkle_overhead(contract_slots, branches_access_events):
    storage_cost = 0
    for [storage_key_hex, _] in contract_slots.items():
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

    return storage_cost


def calculate_slots_read_verkle_savings(contract_slots, branches_access_events):
    return 0


def calculate_call_opcode_verkle_savings(calls_performed):
    return 0


def calculate_create2_opcode_verkle_savings(contract_slots, branches_access_events):
    return 0


def get_name(address, names):
    if address not in names or names[address] is None:
        return address
    else:
        short_address = "(" + address[:8] + "..." + address[38:] + ")"
        return names[address] + " " + short_address


def print_results(results, dumpall):
    for address in results['per_contract_result']:
        result = results['per_contract_result'][address]
        if result['code_size'] > 0:
            codeInfo = f"bytes:{result['code_size']} chunks:{result['code_size_chunks']} max:{result['max_chunk']}"
        else:
            codeInfo = f"max_chunk:{result['max_chunk']}"

        dumpallSuffix = ""
        if dumpall:
            dumpallSuffix = f", all={','.join(map(str, result['chunks'][result['addrress']].keys()))}"

        print(
            f"{result['contract_name']} code:({codeInfo} accessed-chunks:{result['num_chunks']}) storage-slots:{len(result['addr_slots'])} [verkle: code={result['addr_code_cost']} + storage={result['addr_storage_cost']}]{dumpallSuffix}"
        )
    print("")
    print("Total Verkle gas effect = " + str(results['total_gas_effect']))


def estimate_verkle_effect(trace_data, names):
    total_gas_effect = 0
    branches_access_events = {}
    results = {
        'per_contract_result': {},
        'total_gas_effect': 0
    }
    # for each address in trace data
    # branches_access_events += {0: True}

    # Dump number of unique slots used by each address
    chunks = trace_data['chunks']
    for addr in chunks:
        max_chunk = max(chunks[addr].keys())
        num_chunks = len(chunks[addr])

        addr_slots = {}
        if addr in trace_data['slots']:
            addr_slots = trace_data['slots'][addr]
        addr_code_cost = calculate_chunks_read_verkle_effect(chunks[addr], branches_access_events)

        addr_storage_cost = 0
        if addr in trace_data['slots']:
            addr_storage_cost = calculate_slots_read_verkle_overhead(trace_data['slots'][addr], branches_access_events)

        #  TODO
        addr_storage_savings = 0

        #  TODO
        call_savings = 0

        code_size_chunks = (trace_data['code_sizes'][addr] + 30) // 31

        contract_name = get_name(addr, names)

        per_contract_result = {
            'contract_name': contract_name,
            'max_chunk': max_chunk,
            'num_chunks': num_chunks,
            'addr_slots': addr_slots,
            'addr_code_cost': addr_code_cost,
            'addr_storage_cost': addr_storage_cost,
            'addr_storage_savings': addr_storage_savings,
            'call_savings': call_savings,
            'code_size': trace_data['code_sizes'][addr],
            'code_size_chunks': code_size_chunks
        }
        results['per_contract_result'][addr] = per_contract_result
        results['total_gas_effect'] = total_gas_effect
    return results
