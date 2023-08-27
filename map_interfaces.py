import pyeapi
import jinja2

with open("hosts.conf") as f:
    switch_list = f.readlines()

switch_db = {}

for switch in switch_list:
    connection = pyeapi.connect(host=switch.rstrip(), transport='https', username='admin', password='admin')
    connection.transport._context.set_ciphers('DHE-RSA-AES256-SHA')
    
    output = connection.execute(['enable', 'show hostname', 'show version'])

    hostname = output['result'][1]['hostname']
    system_mac = output['result'][2]['systemMacAddress'].replace(':','')

    output = connection.execute(['enable', 'show running-config'], 'text')

    with open(f"./project/configs/{hostname}_{system_mac}.cfg", "w") as config:
        config.write(output['result'][1]['output'])
    
    switch_db[f'{hostname}_{system_mac}'] = {
        'host': f'{hostname}_{system_mac}',
        'interfaces': {}
    }
    
    
    output = connection.execute(['enable', 'show lldp neighbors detail'])

    for interface, neighbor_info in output['result'][1]['lldpNeighbors'].items():

        if 'Man' not in interface:
            # Remote Host
            remote_hostname = neighbor_info['lldpNeighborInfo'][0]['systemName']
            # Remote Chassis ID
            remote_system_mac = neighbor_info['lldpNeighborInfo'][0]['chassisId'].replace('.','')
            switch_db[f'{hostname}_{system_mac}']['interfaces'][interface] = {}
            switch_db[f'{hostname}_{system_mac}']['interfaces'][interface]['remote_host'] = f'{remote_hostname}_{remote_system_mac}'
            # Remote Interface
            remote_interface = neighbor_info['lldpNeighborInfo'][0]['neighborInterfaceInfo']['interfaceId_v2']
            switch_db[f'{hostname}_{system_mac}']['interfaces'][interface]['remote_interface'] = remote_interface

temp_endpoint_list =  []

for host, host_info in switch_db.items():
    for interface, neighbor_info in host_info['interfaces'].items():
        # print(host, interface)
        try:
            if neighbor_info["remote_interface"] in switch_db[neighbor_info["remote_host"]]['interfaces']:
                local_interface = f'{host}:{interface.replace("Ethernet","et")}'
                remote_interface = f'{neighbor_info["remote_host"]}:{neighbor_info["remote_interface"].replace("Ethernet","et")}'
                # print(local_interface)
                # print(remote_interface)
                temp_endpoint_list.append((local_interface,remote_interface))
        except KeyError:
            pass

endpoint_list = set(tuple(sorted(endpoint)) for endpoint in temp_endpoint_list)
host_list = list(switch_db.keys())

kwargs = {
    'endpoints': endpoint_list,
    'nodes': host_list
}

templateLoader = jinja2.FileSystemLoader(searchpath="./templates/")
templateEnv = jinja2.Environment(loader=templateLoader)
TEMPLATE_FILE = "topology.jinja2"
template = templateEnv.get_template(TEMPLATE_FILE)
output = template.render(**kwargs)  # this is where to put args to the template renderer

with open(f"./project/topology.yml", "w") as topology:
    topology.write(output)
