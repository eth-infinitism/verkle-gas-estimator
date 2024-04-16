def print_results(results, dumpall):
    for address in results['per_contract_result']:
        result = results['per_contract_result'][address]
        # if result['code_size'] == -1:
        #     code_info = f"max_chunk:{result['max_chunk']}"
        # elif result['code_size'] > 0:
        #     code_info = f"chunks:{result['code_size_chunks']} bytes:{result['code_size']} max:{result['max_chunk']}"
        # else:
        #     code_info = "failed to get contract size"

        print(result['contract_name'])
        print('Code Access')
        print(f"accessed chunks: {result['num_chunks']}")
        print(f"accessed chunks verkle cost: {result['addr_code_cost']}")
        print('')
        print('Storage Access')
        print(f"storage slots verkle cost (diff): {result['addr_storage_difference']}")
        print('')
        print('Address Warming')
        print(f"CALL with value: {result['call_opcode_with_value_savings']}")
        print(f"Others: {result['address_touching_opcode_count']}")
        print('')
        print('CREATE2')
        print(f"cost difference: {result['create2_opcode_cost_difference']}")
        if dumpall:
            print(f", all chunks={','.join(map(str, result['chunks'][result['addrress']].keys()))}")
        print("")
        print("")
    print("Total Verkle gas effect = " + str(results['total_gas_effect']))


def print_storage_access():
    return 0
