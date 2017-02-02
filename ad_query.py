#!/usr/bin/env python3

import argparse
import pickle
import ldap3
import json
from sys import exit
from DMSconfig import ad_string, ad_address, ad_user, ad_password

# active_badge_ad_string = '(&(objectClass=person)(|(userAccountControl=512)(userAccountControl=66048)))'
active_badge_ad_string = '(&(objectClass=person))'


def get_attributes(host, attributes, username, password, ad_string, max_results):
    if max_results == 0: max_results = None
    if len(attributes) == 0:
        attributes = ldap3.ALL_ATTRIBUTES

    server = ldap3.Server(host, get_info=ldap3.ALL)
    conn = ldap3.Connection(server, user=username, password=password, authentication=ldap3.NTLM)
    conn.bind()
    entry_list = conn.extend.standard.paged_search("ou=Members,dc=dms,dc=local", ad_string, attributes=attributes, paged_size=1000, generator=False)

    if len(conn.entries) < 1: return []
    
    # get attribute names to use later as dict keys (there must be a better way to do this)
    # also this gets the attribute names specifically from the first entry, which is not ideal
    attribute_names = []
    for a in conn.entries[0]:
        attribute_names.append(a.key)

    results = []
    for entry in conn.entries:
        result = {}
        for a in attribute_names:
            try:
                result[str(entry[a].key)] = str(entry[a].value)
            except(ldap3.core.exceptions.LDAPKeyError): # attribute names are retrieved from the first entry, but not all entries have the same attributes
                pass
        results.append(result)
        if max_results and len(results) >= max_results:
            break

    return results


def get_attribute_names(host, username, password):
    server = ldap3.Server(host, get_info=ldap3.ALL)
    conn = ldap3.Connection(server, user=username, password=password, authentication=ldap3.NTLM)
    conn.bind()
    conn.search("ou=Members,dc=dms,dc=local", ad_string, attributes=ldap3.ALL_ATTRIBUTES, paged_size=1)
    result = conn.entries[0]
    
    attribute_names = []
    for a in result:
        attribute_names.append(a.key)

    return attribute_names


# whyyyyy is this still only twice as fast as querying for all active badges??
# by the way, this won't function reliably until all badges are zero-stripped in ad itself
def query_badge(host, username, password, badge):
    badge = str(badge).lstrip('0')
    ad_string = '(&(objectClass=person)(|(userAccountControl=512)(userAccountControl=66048))(employeeID={}))'.format(badge)

    result = get_attributes(
        host=host,
        attributes='employeeID',
        username=username,
        password=password,
        ad_string=ad_string,
        max_results=1
    )

    return True if len(result) > 0 else False


def write_to_pickle_file(filepath, data):
    with open(filepath, 'wb') as handle:
        pickle.dump(data, handle)


def main():
    parser = argparse.ArgumentParser(
        description='Retrieve badges and other attributes from an active directory server',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument('-H', '--host', type=str, help='Hostname of active directory server to query', default=ad_address)
    parser.add_argument('-a', '--attributes', type=str, help='Attributes to retrieve', nargs='+', default=[])
    parser.add_argument('-u', '--username', type=str, help='Username for active directory', default=ad_user)
    parser.add_argument('-p', '--password', type=str, help='Password for active directory', default=ad_password)
    parser.add_argument('-n', '--max-results', type=int, help='Maximum number of results to return (0 is umlimited)', default=0)
    
    parser.add_argument('-A', '--show-attributes', action='store_true', help='Suppress normal output. Instead, output all available attribute names')
    parser.add_argument('-B', '--verify-badge', type=str, help='Suppress normal output. Instead, validate a badge against active directory and return True or False')

    format_group = parser.add_mutually_exclusive_group()
    format_group.add_argument('-c', '--csv', help='Format output in CSV', action='store_const', dest='output_format', const='csv')
    format_group.add_argument('-j', '--json', help='Format output in JSON', action='store_const', dest='output_format', const='json')
    format_group.add_argument('-b', '--filename', help='Output to binary pickle file', type=str)
    parser.set_defaults(output_format='csv')

    args = parser.parse_args()

    # just verify a badge and then return
    if args.verify_badge:
        result = query_badge(
            host=args.host,
            username=args.username,
            password=args.password,
            badge=args.verify_badge
        )
        print(result)
        exit(0) if result == True else exit(1)

    # don't output to stdio if a binary (pickle) output file is given
    if args.filename:
        args.output_format = None

    # just output attribute names and then return
    if args.show_attributes:
        attribute_names = get_attribute_names(host=args.host, username=args.username, password=args.password)
        attribute_names.sort()
        for a in attribute_names:
            print(a)
        return

    # run the query and store the result
    result = get_attributes(
        host=args.host,
        attributes=args.attributes,
        username=args.username,
        password=args.password,
        ad_string=active_badge_ad_string,
        max_results=args.max_results
    )

    # output the result in the specified format

    if args.output_format == 'json':
        result = json.dumps(result)
        print(result)

    elif args.output_format == 'csv':
        for r in result:
            keys = [key for key in r]
            keys.sort()
            for key in keys:
                print(r[key], end=", ")
            print("\b\b  ")

    elif args.filename:
        write_to_pickle_file(args.filename, result)


if __name__ == "__main__":
    main()
