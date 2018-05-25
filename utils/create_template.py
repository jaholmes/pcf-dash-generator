#!/usr/bin/env python3
import argparse
import json

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source_file", help='file to create template from', required=True)
    parser.add_argument("--template_mappings", help='json file with strings to replace', required=True)    
    args = parser.parse_args()
    print(args)
    return args

    
def create_template(source_file, template_mappings):
    with open(source_file, 'r', encoding='utf-8') as myfile:
        source=myfile.read()

    for mapping in template_mappings:
        source = source.replace(mapping[0], mapping[1])

    with open(source_file + '.output', 'w', encoding='utf-8') as myfile:
        myfile.write(source)

    print("wrote output to: " + source_file + '.output')
    
def run():
    args = parse_args()
    with open(args.template_mappings, 'r', encoding='utf-8') as myfile:
        template_mappings=json.load(myfile)
    
    create_template(args.source_file, template_mappings)
    
if __name__ == '__main__':
    run()
