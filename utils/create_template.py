import argparse

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-source_file", help='file to create template from', required=True)
    parser.add_argument("-v", "--verbose", action='store_true', dest="verbose", default=False, help="print verbose output")
    args = parser.parse_args()
    if args.verbose:
        print(args)
    return args

template_mappings = [
    ['Tier_system_adpcf18_com', '${TIER_NAME}'],
    ['diego_cell|073c50d0-3dad-48eb-a1e0-3c495c1115d2|10.206.0.41', 'diego_cell|${DIEGO_CELL_0_GUID}|{DIEGO_CELL_0_IP_0}'],
    ['diego_cell|27ea918f-9198-40ee-b262-0df5a57671fb|10.206.0.42', 'diego_cell|${DIEGO_CELL_1_GUID}|{DIEGO_CELL_1_IP_0}'],
    ['diego_cell|760c2862-b5c0-4e78-aa76-d365ced1f150|10.206.0.40', 'diego_cell|${DIEGO_CELL_2_GUID}|{DIEGO_CELL_2_IP_0}'],
    ['diego_brain|55a231ab-eebb-4c86-b964-79316e9a75d0|10.206.0.39', 'diego_brain|${DIEGO_BRAIN_GUID}|${DIEGO_BRAIN_IP}'],
    ['router|4079754e-cb02-4396-9f09-2088612813b7|10.206.0.3', 'router|${ROUTER_GUID}|${ROUTER_IP}'],
    ['diego_database|d234e2f3-f136-460a-a4eb-bc1cde38b46f|10.206.0.38', 'diego_database|${DIEGO_DATABASE_GUID}|${DIEGO_DATABASE_IP}'],
    ['cf-16dbe69b77fa027ffdb4', '${RESOURCES_PARENT_FOLDER}']
]
    
def create_template(source_file):
    with open(source_file, 'r', encoding='utf-8') as myfile:
        source=myfile.read()
    
    for mapping in template_mappings:
        source = source.replace(mapping[0], mapping[1])

    print('source: ' + source)
    
    with open(source_file + '.output', 'w', encoding='utf-8') as myfile:
        myfile.write(source)

    
def run():
    args = parse_args()
    create_template(args.source_file)
    
if __name__ == '__main__':
    run()
