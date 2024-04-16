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

#  Current (EIP-2929, EIP-2200) constants
SSTORE_SET_GAS = 20000
WARM_STORAGE_READ_COST = 100


def calculate_deployment_gas_effect(contract_size):
    code_chunks = contract_size // 31
    code_subtrees = math.ceil((code_chunks + CODE_OFFSET) / 256)
    return CHUNK_FILL_COST * code_chunks + SUBTREE_EDIT_COST * code_subtrees


def calculate_chunks_read_verkle_effect(contract_chunks):
    branches_access_events = {0: True}  # subtree 0 is always initialized

    code_cost = 0
    for [contract_chunk, _] in contract_chunks.items():
        code_cost += WITNESS_CHUNK_COST
        branch_id = contract_chunk // 256
        if branch_id not in branches_access_events:
            branches_access_events[branch_id] = True
            code_cost += WITNESS_BRANCH_COST
    return code_cost


def get_slot_verkle_id(storage_key_hex):
    storage_key = int(storage_key_hex, 16)
    # special storage for slots 0..64
    if storage_key < (CODE_OFFSET - HEADER_STORAGE_OFFSET):
        pos = HEADER_STORAGE_OFFSET + storage_key
    else:
        pos = MAIN_STORAGE_OFFSET + storage_key
    branch_id = pos // VERKLE_NODE_WIDTH
    sub_id = pos % VERKLE_NODE_WIDTH

    return [branch_id, sub_id]


#  subtract current costs and apply new costs
def calculate_slots_verkle_difference(contract_slots):
    accessed_subtrees = {0: True}  # subtree 0 is always initialized
    accessed_leaves = {}
    edited_subtrees = {}
    edited_leaves = {}

    new_costs = 0
    old_cost = 0
    for slot_id in contract_slots:
        slot = contract_slots[slot_id]
        [branch_id, sub_id] = get_slot_verkle_id(slot_id)
        for opcode in slot:
            old_cost += opcode['gas']
            if opcode['opcode'] == 'SSTORE':
                if branch_id in edited_subtrees and sub_id in edited_leaves:
                    new_costs += WARM_STORAGE_READ_COST  # this is not explicitly specified by EIP-4762
                if branch_id not in edited_subtrees:
                    new_costs += SUBTREE_EDIT_COST
                    edited_subtrees[branch_id] = True
                if sub_id not in edited_leaves:
                    new_costs += CHUNK_EDIT_COST
                    edited_leaves[branch_id] = True
                    if opcode['gas'] == SSTORE_SET_GAS:  # considering pre-verkle value 0 as equivalent to 'None'
                        new_costs += CHUNK_FILL_COST

            elif opcode['opcode'] == 'SLOAD':
                if branch_id in accessed_subtrees and sub_id in accessed_leaves:
                    new_costs += WARM_STORAGE_READ_COST  # this is not explicitly specified by EIP-4762
                if branch_id not in accessed_subtrees:
                    new_costs += WITNESS_BRANCH_COST
                    accessed_subtrees[branch_id] = True
                if sub_id not in accessed_leaves:
                    new_costs += WITNESS_CHUNK_COST
                    accessed_leaves[branch_id] = True
            else:
                raise Exception("Unknown opcode " + slot['opcode'])
    return new_costs - old_cost


#  it appears that all the refund-based logic in EIP-2200 and EIP-2929 is removed in EIP-4762
def calculate_slots_read_verkle_removed_refunds(contract_slots):
    refunds = 0
    for slot_id in contract_slots:
        for opcode in contract_slots[slot_id]:
            refunds += opcode['refund']
    return refunds


def calculate_call_opcode_verkle_savings(calls_performed):
    return 0


def calculate_create2_opcode_verkle_savings(contract_slots):
    return 0


def get_name(address, names):
    if address not in names or names[address] is None:
        return address
    else:
        short_address = "(" + address[:8] + "..." + address[38:] + ")"
        return names[address] + " " + short_address


def estimate_verkle_effect(trace_data, names):
    results = {
        'per_contract_result': {},
        'total_gas_effect': 0
    }

    # Dump number of unique slots used by each address
    chunks = trace_data['chunks']
    for addr in chunks:
        max_chunk = max(chunks[addr].keys())
        num_chunks = len(chunks[addr])

        addr_code_cost = calculate_chunks_read_verkle_effect(chunks[addr])

        addr_storage_difference = 0
        addr_storage_removed_refund = 0
        if addr in trace_data['slots']:
            addr_slots = trace_data['slots'][addr]
            addr_storage_difference = calculate_slots_verkle_difference(addr_slots)
            addr_storage_removed_refund = calculate_slots_read_verkle_removed_refunds(addr_slots)

        call_savings = calculate_call_opcode_verkle_savings(trace_data)

        code_size_chunks = (trace_data['code_sizes'][addr] + 30) // 31

        contract_name = get_name(addr, names)

        per_contract_result = {
            'contract_name': contract_name,
            'max_chunk': max_chunk,
            'num_chunks': num_chunks,
            'call_opcode_with_value_count': -1,
            'address_touching_opcode_count': -1,
            'create2_opcode_bytes_written': -1,
            'addr_code_cost': addr_code_cost,
            'addr_storage_difference': addr_storage_difference,
            # EIP-2200 heavily relies on refunds which is superseded by EIP-4762
            'addr_storage_removed_refund': addr_storage_removed_refund,
            'call_savings': call_savings,
            'code_size': trace_data['code_sizes'][addr],
            'code_size_chunks': code_size_chunks
        }
        results['per_contract_result'][addr] = per_contract_result
        results['total_gas_effect'] += \
            (addr_code_cost +
             addr_storage_difference -
             addr_storage_removed_refund -
             call_savings
             )
    return results
