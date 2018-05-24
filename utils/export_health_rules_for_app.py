#!/usr/bin/env python3
import requests
import xml.dom.minidom
import argparse

def get_controller_url(host, port, ssl_enabled):
    if ssl_enabled is True:
        controller_url = 'https://'
    else:
        controller_url = 'http://'
    controller_url += host
    if port:
        controller_url += ':' + port
    return controller_url

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_host', help='the controller host', required=True)
    parser.add_argument('--controller_port', help='the controller port', required=True)
    parser.add_argument('--controller_ssl', help='True if ssl is enabled', default=False)
    parser.add_argument('--account_name', help='the controller account name', required=True, default='customer1')
    parser.add_argument('--user_name', help='the controller username', required=True)
    parser.add_argument('--user_pass', help='the controller user password', required=True)
    parser.add_argument('--app', help='the Appd app to export health rules from', required=True)
    args = parser.parse_args()
    print('args: ' + str(args))
    return args

def write_hrs(args):
    url = get_controller_url(args.controller_host, args.controller_port, args.controller_ssl) + '/controller/healthrules/' + args.app
    print('url: ' + url)
    response = requests.get(url, auth=(args.user_name + '@' + args.account_name, args.user_pass))
    response.raise_for_status();
    print('response: ' + str(response))
    
    xml_file = args.app + '-healthrules' + '.xml'
    xml_string = xml.dom.minidom.parseString(str(response.content.decode("utf-8")))
    pretty_xml_string = xml_string.toprettyxml()
    with open(xml_file, 'w', encoding='utf-8') as file:    
        file.write(pretty_xml_string)
    print('wrote hrs to: ' + xml_file)


def run():
    args = parse_args()
    write_hrs(args)
    
if __name__ == '__main__':
    run()
