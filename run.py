#!/usr/bin/env python
# coding=utf-8
import cmd
import getpass
import tarfile
import codecs
import subprocess
import re
import pprint
import json

from os import listdir, mkdir, system, unlink, remove
from os.path import isfile, isdir, join, getmtime, basename
from dateutil import tz
from tabulate import tabulate

from lib import style, sslsplit, util, core, hostapd


class TlsSharkInteractive(cmd.Cmd):
    intro = """

     _    _ _          _____                      _                   ,,__
    | |  | (_)        /  __ \                    | |        ..  ..   / o._)                   .---.
    | |  | |_ _ __ ___| /  \/ __ _ _ __ ___   ___| |       /--'/--\\  \-'||        .----.    .'     '.
    | |/\| | | '__/ _ \ |    / _` | '_ ` _ \ / _ \ |      /        \\_/ / |      .'      '..'         '-.
    \  /\  / | | |  __/ \__/\ (_| | | | | | |  __/ |    .'\\  \\__\\  __.'.'     .'          -._
     \/  \/|_|_|  \___|\____/\__,_|_| |_| |_|\___|_|      )\ |  )\ |      _.'
                                                         // \\ // \\
                                                        ||_  \\|_  \\_
        [  Author  => Querdos  ]                        '--' '--'' '--'
        [  Version => 1.0      ]

    """

    # Initial configuration
    prompt = "wirecamel> "

    # Hostapd default param
    hostapd_options = {
        'interface': '',
        'driver': '',
        'ssid': '',
        'channel': '',
        'macaddr_acl': '',
        'hw_mode': '',
        'auth_algs': '',
        'wpa': '',
        'wpa_key_mgmt': '',
        'wpa_passphrase': '',
        'wpa_pairwise': '',
        'logger_syslog': '',
        'logger_syslog_level': '',
        'logger_stdout': '',
        'logger_stdout_level': ''
    }

    # Attributes
    filters = {
        'source_ip': '',
        'source_port': '',
        'dest_ip': '',
        'dest_port': '',
        'host': ''
    }

    # Main configuration variables
    config = {
        'interface': '',
        'save_dir': 'saved_logs/',
        'temp_iptables': '/tmp/wirecamel_iptables_restore',
        'hostapd_conf': 'conf/hostapd.conf',
        'iptables_conf': 'conf/iptables-configuration.bak',
        'max_result': None,
        'range_result': []
    }

    sslsplit_config = {
        'main': 'sslsplit/',
        'log_dir': 'sslsplit/logs/',
        'keys': 'sslsplit/keys/',
        'connections': 'sslsplit/connections.log'
    }

    sslsplit_started = False
    files_association = {}
    headers = {}
    subhostapd = None
    subssl = None

    # Initial configuration
    def preloop(self):
        # Checking if dependencies are installed
        util.check_dependencies()

        # Creating SSL Split directory structure if needed
        sslsplit.create_structure(self.sslsplit_config)

        # Generate certificates if needed
        sslsplit.generate_certs(self.sslsplit_config['keys'])

        # Reading hostapd configuration file
        self.hostapd_options = hostapd.load_hostapd_conf(self.config['hostapd_conf'])

        # Clearing terminal
        system("clear")

    # Allow the user to configure interfaces (access point and internet access)
    def do_init_interfaces(self, value):
        # Retrieving interfaces (wireless and wired)
        wireless_interfaces = util.get_wireless_interface()
        net_interfaces = util.get_network_interfaces()

        # If only one interface, selecting it for the access point
        # TODO: One interface ?
        if len(wireless_interfaces) == 1:
            # Setting the interface for AP in conf
            self.config['interface'] = wireless_interfaces[0]
        else:
            # Printing available interfaces
            print
            for wi in wireless_interfaces:
                print("[{}] {}".format(wireless_interfaces.index(wi), wi))

            print
            user_choice = -1

            # Asking to select a wireless interface for the access point
            while user_choice < 0 or user_choice >= len(wireless_interfaces):
                user_choice = raw_input("Select a wireless interface for the access point: ")
                try:
                    user_choice = int(user_choice)
                    self.config['interface'] = wireless_interfaces[user_choice]
                except ValueError:
                    user_choice = -1
                    continue

            # Write iptables configuration
            util.write_iptables_conf(wireless_interfaces[user_choice], net_interfaces[0])

        exit(1)
        print(value)

    # Print initial configuration and allow the user to edit it
    def do_init_config(self, value):
        """init_config
        Print initial configuration parameters and their values or change it by
        specifying which one and with which value
        """
        # If no arguments specified, just printing initial config
        if not value:
            table_print = []
            for conf_key in self.config:
                if None is not self.config[conf_key]:
                    table_print.append([conf_key, self.config[conf_key]])
                else:
                    table_print.append([conf_key, 'Not set'])

            print(tabulate(table_print, tablefmt="fancy_grid"))
        else:
            arguments = value.split(" ")
            if len(arguments) != 1:
                if arguments[0] in self.config:
                    # Specific handling for range result
                    if arguments[0] == 'range_result':
                        if len(arguments) == 3:
                            try:
                                if 0 <= int(arguments[1]) < int(arguments[2]):
                                    self.config[arguments[0]] = [int(arguments[1]), int(arguments[2])]
                                else:
                                    style.fail("Usage: init_config range_result a b (0 <= a < b)")
                            except ValueError:
                                style.fail("Values must be integer")
                        else:
                            style.fail("Usage: init_config range_result min_value max_value")

                    # Specific handling for uri
                    elif arguments[0] == 'save_dir':
                        if value.startswith("save_dir '"):
                            self.config['save_dir'] = util.purify_uri(value[len("save_dir '"):-1])
                        elif value.startswith("save_dir \""):
                            self.config['save_dir'] = util.purify_uri(value[len("save_dir \""):-1])
                        else:
                            self.config['save_dir'] = util.purify_uri(arguments[1])
                    else:
                        # Setting value for the given parameter
                        self.config[arguments[0]] = arguments[1]
                else:
                    style.fail("Unknown parameter.")
            else:
                style.fail("Usage: init_config | init_config param value")

    # Completion for init_config
    def complete_init_config(self, text, line, begidx, endidx):
        return [i for i in self.config if i.startswith(text)]

    # Print filters and allow the user to edit it
    def do_filters(self, value):
        if not value:
            table_print = []
            for fil in self.filters:
                if len(self.filters[fil]) == 0:
                    table_print.append([fil, 'Not set'])
                else:
                    table_print.append([fil, self.filters[fil]])

            print(tabulate(table_print, tablefmt="fancy_grid"))
        else:
            arguments = value.split(" ")
            if len(arguments) == 2:
                if arguments[0] in self.filters:
                    self.filters[arguments[0]] = arguments[1]
                else:
                    style.fail("Unknown filter")
            else:
                style.fail("Usage: filters | filters filter_name filter_value")

    # Completion for fitlers
    def complete_filters(self, text, line, begidx, endidx):
        return [i for i in self.filters if i.startswith(text)]

    # Print Acess Point (Hostapd) configuration
    def do_ap_config(self, value):
        """ap_config
        Print the access point configuration and allow the user to change default values
        """
        if not value:
            table_print = []
            for key in self.hostapd_options:
                table_print.append([key, self.hostapd_options[key]])

            print("\n=================================")
            print("\tHostapd configuration")
            print("=================================")
            print(tabulate(table_print, tablefmt='fancy_grid'))
        else:
            arguments = value.split(" ")
            if len(arguments) == 2:
                if arguments[0] in self.hostapd_options:
                    self.hostapd_options[arguments[0]] = arguments[1]
                    hostapd.save_config(self.hostapd_options, 'conf/hostapd.conf')
                else:
                    style.fail("Usage: ap_config | ap_config config_param value")
            else:
                style.fail("Usage: ap_config | ap_config config_param value")

    # Start SSLSplit
    def do_start_sslsplit(self, line):
        """start_sslsplit
        Start SSL Split as an access point
        """
        if len(self.config['interface']) != 0:
            # Checking processes with airmon-ng
            res = subprocess.call(
                "airmon-ng check kill".split(" "),
                stdout=subprocess.PIPE
            )
            style.print_call_info(res, "airmon-ng", "Killed unwanted processes.")

            # Unblocking wifi if needed
            res = subprocess.call("rfkill unblock wifi".split(" "), stdout=subprocess.PIPE)
            style.print_call_info(res, "rfkill", "Unblocked Wifi (Soft and Hardware mode)")

            # Saving actual iptables rules to restore it after stopping the ap
            res = subprocess.call(
                "iptables-save > {}".format(self.config['temp_iptables']).split(" "),
                stdout=subprocess.PIPE
            )
            style.print_call_info(res, "iptables", "Saved actual iptables rules")

            # Flushing iptables
            res = subprocess.call("iptables -t nat -F".split(" "), stdout=subprocess.PIPE)
            style.print_call_info(res, "iptables", "Flushed iptables rules")

            # Starting dnsmasq service
            res = subprocess.call("service dnsmasq start".split(" "), stdout=subprocess.PIPE)
            style.print_call_info(res, "dnsmasq", "Started dnsmasq service")

            # Loading iptables rules for SSLSplit and hostapd
            res = subprocess.call(
                "iptables-restore {}".format(self.config['iptables_conf']).split(" ")
            )
            style.print_call_info(res, 'iptables', 'Updated iptables rules for SSL Split')

            # TODO: Remove
            # iptables rules for SSLSplit
            # iptables_rules = [
            #     "iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 8080",
            #     "iptables -t nat -A PREROUTING -p tcp --dport 443 -j REDIRECT --to-ports 8443",
            #     "iptables -I INPUT -p tcp -m state --state NEW -m tcp --dport 80 -j ACCEPT",
            #     "iptables -I INPUT -p tcp -m state --state NEW -m tcp --dport 443 -j ACCEPT",
            #     "iptables -I INPUT -p tcp -m state --state NEW -m tcp --dport 8443 -j ACCEPT",
            #     "iptables -I INPUT -p tcp -m state --state NEW -m tcp --dport 8080 -j ACCEPT"
            # ]
            # for command in iptables_rules:
            #     subprocess.call(command.split(" "), stdout=subprocess.PIPE)
            # style.print_call_info(0, "iptables", "Updated iptables rules for SSLSplit")

            # iptables rules for hostapd
            # iptables_rules = [
            #     "iptables -t nat -A POSTROUTING -o wlan1 -j MASQUERADE",
            #     "iptables -A FORWARD -i wlan0 -o wlan1 -j ACCEPT"
            # ]
            # for command in iptables_rules:
            #     subprocess.call(command.split(" "), stdout=subprocess.PIPE)
            # style.print_call_info(0, "iptables", "Updated iptables rules for hostapd")

            # Confiuguring interface
            res = subprocess.call(
                "ifconfig {} 10.0.0.1/24 up".format(self.config['interface']).split(" "),
                stdout=subprocess.PIPE
            )
            style.print_call_info(res, "ifconfig", "Configured interface")

            # Enabling IP forward
            res = subprocess.call("sysctl -w net.ipv4.ip_forward=1".split(" "), stdout=subprocess.PIPE)
            style.print_call_info(res, "ip_forward", "Enabled IP forwarding")

            # Starting hostapd
            self.subhostapd = subprocess.Popen(
                ['xterm', '-T', 'Hostapd console', '-hold', '-e', 'hostapd', '-d', 'conf/hostapd.conf']
            )
            style.print_call_info(0, "hostapd", "Started hostapd")

            # Starting SSLSPlit
            self.subssl = subprocess.Popen(
                ['xterm', '-T', 'SSL Split console', '-e', './start_sslsplit.sh']
            )

            # Setting started for sslsplit
            self.sslsplit_started = True
        else:
            style.fail("Please setup interface for the access point")

    # Stop SSL Split and clean
    def do_stop_sslsplit(self, line):
        """stop_sslsplit
        Stop the access point and SSL Split
        """
        if not self.sslsplit_started:
            style.fail("SSL Split and hostapd not started")
        else:
            # Killing previously started process
            self.subssl.kill()
            self.subhostapd.kill()

            # Stopping hostapd
            res = subprocess.call("service hostapd stop".split(" "), stdout=subprocess.PIPE)
            style.print_call_info(0, "hostapd", "Stopped hostapd service")

            # Restoring iptables rules
            res = subprocess.call("iptables-restore /tmp/wirecamel_iptables_restore".split(" "), stdout=subprocess.PIPE)
            unlink("/tmp/wirecamel_iptables_restore")
            style.print_call_info(res, "iptables", "Restored iptables nat rules")

            # Disabling ip forwarding
            res = subprocess.call("sysctl -w net.ipv4.ip_forward=0".split(" "), stdout=subprocess.PIPE)
            style.print_call_info(res, "ip_foward", "Disabled IP forwarding")

            # Restarting network manager
            res = subprocess.call("service NetworkManager start".split(" "), stdout=subprocess.PIPE)
            style.print_call_info(res, "NetworkManager", "Started NetworkManager")

            # Setting sslsplit started to false
            self.sslsplit_started = False

    # Reset Filters
    def do_reset_filters(self, line):
        """reset_filters
        Reset filters (Source IP, Source Port, etc.)
        """
        for key in self.filters.keys():
            self.filters[key] = ''

    # Log file parsing
    def do_parse(self, value):
        """parse [logfile_id]
        Parse the given log file id.
        You must run show_connection first in order to retrieve all files in sslsplit logs directory
        """
        if value:
            if len(self.files_association) == 0:
                style.fail(
                    "The list is empty. Please first use show_connections to parse existant files."
                )
            elif value in self.files_association:
                log_filename = self.files_association[str(value)]

                # Opening the file
                with open(self.sslsplit_config['log_dir'] + log_filename) as log_file:
                    m = re.match(r'(.*)-(.*),(.*)-(.*),(.*)\.log', log_filename)
                    if m:
                        # Parsing the request
                        self.headers = core.parse_logfile(log_file)
                    else:
                        # Error
                        print("Incorrect file format.\n")
            else:
                style.fail("This id is not in the list. Please launch show_connections for a list of id")

        else:
            style.fail("Usage: parse log_id (can be retrieved after showing connections)")

    # Allow the user to save responses, requests or stream
    def do_save(self, value):
        """save [requests|responses|stream]
        Save to a save directory either all responses, requests or the entire stream
        """
        # Handling saving all
        if len(value.split(" ")) == 1 and value.split(" ")[0] == 'all':
            for filename in self.files_association:
                with open("{}{}".format(self.sslsplit_config['log_dir'], filename)) as file_object:
                    # TODO
                    headers = core.parse_logfile(file_object)

        # Handling requests, responses and stream saving all
        elif len(self.headers) != 0:
            if value:
                # Checking arguments
                arguments = value.split(" ")
                if len(arguments) == 1 and arguments[0] in ['requests', 'responses', 'stream']:
                    # Asking for filename
                    filename = ""
                    while len(filename) == 0:
                        filename = raw_input("Filename: ")
                        if len(filename) != 0 and isfile("{}{}".format(self.config['save_dir'], filename)):
                            style.fail(
                                "{}{} already exists, please choose a new filename".format(
                                    self.config['save_dir'], filename
                                )
                            )
                            filename = ""

                    # Checking if saving directory exists and create one if needed
                    if not isdir(self.config['save_dir']):
                        mkdir(self.config['save_dir'])

                    # Opening the file for write operation
                    save_file = codecs.open("{}{}".format(self.config['save_dir'], filename), 'w', encoding='utf-8')

                    # Checking what the user want to save
                    table_tosave = []
                    if arguments[0] == 'stream':
                        save_file.write(core.printable_headers(self.headers))
                    else:
                        save_file.write(core.printable_headers(self.headers[arguments[0]]))

                    # Closing the file
                    style.print_call_info(0, "", "Saved successfuly ({}{})".format(self.config['save_dir'], filename))
                    save_file.close()
                else:
                    style.fail("Usage: save [requests|responses|stream]")
            else:
                style.fail("Usage: save [requests|responses|stream]")
        else:
            style.fail("No log selected, please run show_connections and parse first")

    # Completion for save command
    def complete_save(self, text, line, begidx, endidx):
        return [i for i in ['requests', 'responses', 'stream', 'all'] if i.startswith(text)]

    # TODO
    def save_all_streams(self, headers):
        pprint.pprint(headers)

    # Allow the user to print responses, requests or the entire stream
    def do_print(self, value):
        """print [requests|responses|stream|filename]
        Print either all responses, requests or the entire stream
        """
        arguments = value.split(" ")

        # Handling filename printing
        if len(arguments) == 2 and arguments[0] == 'filename':
            if arguments[1] in self.files_association:
                print(self.files_association[str(arguments[1])])
            else:
                style.fail(
                    "No id found in association array. Please use show_connection for more "
                    "information")

        elif len(self.headers) != 0:
            if value:
                # Checking arguments
                arguments = value.split(" ")
                if 1 == len(arguments) and arguments[0] in ['requests', 'responses', 'stream']:
                    # Checking what the user wants to print
                    if arguments[0] == 'stream':
                        print(core.printable_headers(self.headers))
                    else:
                        print(core.printable_headers(self.headers[arguments[0]]))
                else:
                    style.fail("Usage: print [requests|responses|stream]")
            else:
                style.fail("Usage: print [requests|response|stream]")
        else:
            style.fail("You need to parse a file first. Please refer to show_connections and parse.")

    # Completion for print command
    def complete_print(self, text, line, begidx, endidx):
        return [i for i in ['requests', 'responses', 'stream', 'filename'] if i.startswith(text)]

    # Print statistics for current session
    def do_stats(self, line):
        if len(self.files_association) != 0:
            stats_table = {}
            for log in self.files_association.values():
                m = re.match(r'(.*)-(.*),(.*)-(.*),(.*)\.log', log)

                # Retrieving number of requests (POST, HEAD, GET, whatever)
                with open(self.sslsplit_config['log_dir']+log) as log_file:
                    content_total = 0
                    total_post = 0
                    total_get = 0
                    total_put = 0
                    total_head = 0

                    try:
                        result = core.parse_logfile(log_file)

                        requests = len(result['requests'])

                        for request in result['requests']:
                            if 'Content-Length' in request:
                                content_total += int(request['Content-Length'])

                            # Methods stats
                            if 'POST' == request['Method']:
                                total_post += 1
                            if 'GET' == request['Method']:
                                total_get += 1
                            if 'PUT' == request['Method']:
                                total_put += 1
                            if 'HEAD' == request['Method']:
                                total_head += 1
                    # TODO: problem with chunked data
                    except ValueError:
                        continue

                # Adding source ip if not present
                if m.group(2) not in stats_table:
                    stats_table[m.group(2)] = {}

                # Checking if destination ip is present
                if m.group(4) not in stats_table[m.group(2)]:
                    stats_table[m.group(2)][m.group(4)] = {
                        'count': requests,
                        'content-total': content_total,
                        'get-total': total_get,
                        'post-total': total_post,
                        'put-total': total_put,
                        'head-total': total_head
                    }
                else:
                    stats_table[m.group(2)][m.group(4)]['count'] += requests
                    stats_table[m.group(2)][m.group(4)]['content-total'] += content_total
                    stats_table[m.group(2)][m.group(4)]['get-total'] += total_get
                    stats_table[m.group(2)][m.group(4)]['post-total'] += total_post
                    stats_table[m.group(2)][m.group(4)]['put-total'] += total_put
                    stats_table[m.group(2)][m.group(4)]['head-total'] += total_head

            # Filling printing table
            table_print = {}
            headers = [
                'Destination IP',
                'Requests',
                'Total Content-Length sent',
                'Total POST',
                'Total GET',
                'Total PUT',
                'Total HEAD'
            ]
            for ipsrc in stats_table:
                if ipsrc not in table_print:
                    table_print[ipsrc] = []

                for ipdst in stats_table[ipsrc]:
                    table_print[ipsrc].append(
                        [
                            ipdst,
                            stats_table[ipsrc][ipdst]['count'],
                            stats_table[ipsrc][ipdst]['content-total'],
                            stats_table[ipsrc][ipdst]['post-total'],
                            stats_table[ipsrc][ipdst]['get-total'],
                            stats_table[ipsrc][ipdst]['put-total'],
                            stats_table[ipsrc][ipdst]['head-total']
                        ]
                    )

            for ipsrc in table_print:
                print("============================")
                print("\t{}".format(ipsrc))
                print("============================")
                print(tabulate(table_print[ipsrc], headers=headers, tablefmt='fancy_grid'))
                print

        else:
            style.fail("Please run show_connections first in order to print statistics.")

    # Show connections made since SSL Split is launched
    def do_show_connections(self, line):
        """show_connections
        Show connections made since SSL Split is launched
        """
        from_zone = tz.gettz('UTC')
        to_zone = tz.gettz('Europe/Paris')

        # Reseting (if needed) headers
        self.headers = {}
        self.files_association = {}

        # Listing all files in dir
        files = [
            f for f in listdir(self.sslsplit_config['log_dir'])
            if isfile(join(self.sslsplit_config['log_dir'], f))
        ]
        files.sort(key=lambda x: getmtime(self.sslsplit_config['log_dir'] + x))

        # Printing informations for each file
        table = []
        headers = ['Id', 'Creation date', 'Source IP', 'Source Port', 'Destination IP', 'Destion Port',
                   'Host', 'Id']

        file_id = 1
        for log_file in files:
            # Checking range
            if len(self.config['range_result']) != 0:
                if file_id not in range(self.config['range_result'][0], self.config['range_result'][1]+1):
                    file_id += 1
                    continue

                # No need to continue if id is greater than the range
                if file_id > self.config['range_result'][1]:
                    break

            # Parsing filename
            file_info = core.parse_logfilename(log_file)

            if len(self.filters['source_ip']) != 0 and self.filters['source_ip'] != file_info['source_ip']:
                continue
            if len(self.filters['source_port']) != 0 and self.filters['source_port'] != file_info['source_port']:
                continue
            if len(self.filters['dest_ip']) != 0 and self.filters['dest_ip'] != file_info['destination_ip']:
                continue
            if len(self.filters['dest_port']) != 0 and self.filters['dest_port'] != file_info['destination_port']:
                continue

            # Parsing file
            with open(self.sslsplit_config['log_dir'] + log_file, 'r') as f:
                # f = open(self.sslsplit_log_dir+file, 'r')
                host = "-"
                for line in f.readlines():
                    mhost = re.findall(r'Host: (.*)\r', line)
                    if len(mhost) != 0:
                        host = mhost[0]
                        break

            if len(self.filters['host']) != 0 and self.filters['host'] != host:
                continue

            # Appending data
            table.append([
                file_id,
                file_info['date'],
                file_info['source_ip'],
                file_info['source_port'],
                file_info['destination_ip'],
                file_info['destination_port'],
                host,
                file_id
            ])
            self.files_association[str(file_id)] = log_file

            # Checking for max result to print
            if self.config['max_result'] is not None and file_id == int(self.config['max_result']):
                break

            file_id += 1

        print(tabulate(table, headers=headers, tablefmt='fancy_grid'))

    # Show information for the given log id (internet protocol, whois)
    def do_show_information(self, value):
        """show_information [log_id]
        Print IP information and whois informations
        """
        if value:
            if len(self.files_association) == 0:
                style.fail(
                    "The list is empty. Please first use show_connections to parse existant files."
                )
            # Checking if value is a correct id
            elif value in self.files_association:
                # Retrieving filename
                log_filename = self.files_association[str(value)]
                m = re.match(r'(.*)-(.*),(.*)-(.*),(.*)\.log', log_filename)

                # Internet Protocol information
                table_ip = [
                    ['Source IP', m.group(2)],
                    ['Source Port', m.group(3)],
                    ['Dest IP', m.group(4)],
                    ['Dest Port', m.group(5)]
                ]

                # Whois informations
                info = util.whois_information(m.group(4))
                table_whois = [
                    ['NetName', info['netname']],
                    ['Organization', info['organization']],
                    ['City', info['city']],
                    ['Country', info['country']]
                ]

                # Printing informations
                print("\n====================================================")
                print("\tInternet Protocol informations")
                print("====================================================")
                print(tabulate(table_ip, tablefmt='fancy_grid'))
                print
                print("====================================================")
                print("\tWhois informations")
                print("====================================================")
                print(tabulate(table_whois, tablefmt='fancy_grid'))
                print
                util.whois_information(m.group(4))
            else:
                style.fail("This id is not a valid one. Please use show_connections for more informations")
        else:
            style.fail("Usage: show_information [log_id]")

    # Do a backup of log files and the connections log file
    def do_backup_and_clean(self, line):
        """backup_and_clean
        Make a backup of all log files in sslsplit-logs directory (saving in the save_dir directory)
        """
        filename = ""
        while len(filename) == 0:
            filename = raw_input("Name for the backup (without extension)? ")

        with tarfile.open(self.config['save_dir']+filename+".gz", "w:gz") as tar:
            tar.add(self.sslsplit_config['log_dir'], arcname=basename(self.sslsplit_config['log_dir']))
            tar.add(self.config['connections_logfile'])

        style.print_call_info(0, "tar", "Saved backup to {}".format(self.config['save_dir']))

        for filetoremove in listdir(self.sslsplit_config['log_dir']):
            if isfile("{}{}".format(self.sslsplit_config['log_dir'], filetoremove)):
                remove("{}{}".format(self.sslsplit_config['log_dir'], filetoremove))

        # Removing connections log file
        if isfile(self.config['connections_logfile']):
            remove(self.config['connections_logfile'])

        style.print_call_info(0, "rm", "Cleaned logs and connections")

    # Base 64 decoding function
    @staticmethod
    def do_base64_decode(value):
        """base64_decode
        Decode a string, base64 encoded
        """
        newvalue = value.decode("base64")
        print newvalue

    # Prettify JSON formatted text
    @staticmethod
    def do_pretty_simplejson(value):
        """pretty_simplejson
        Prettify JSON (simple) input
        """
        table = []
        json_data = json.loads(value)
        for key in json_data.keys():
            table.append([key, json_data[key]])

        print(tabulate(table, tablefmt="fancy_grid"))

    # Prettify URI
    def do_pretty_uri(self, value):
        if value:
            print(value.replace("&", "\n").replace("=", " = "))
        else:
            style.fail("Usage: pretty_uri [uri]")

    def emptyline(self):
        pass

    # Exit the program
    def do_bye(self, line):
        """bye
        Exit the program"""
        exit(0)

    def do_EOF(self, line):
        """do_EOF
        End Of File function
        """
        return True


if __name__ == "__main__":
    # Checking if running as root
    if 'root' != getpass.getuser():
        print("Root privileges needed.")
        exit(1)

    TlsSharkInteractive().cmdloop()
