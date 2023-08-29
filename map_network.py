import pyeapi
import jinja2
import yaml

def load_config():
    """Returns the config.yml file as a python dictionary"""
    with open("config.yml", "r") as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    return data

def map_network(api_user, api_password, switch_list):
    """Writes all running configs to clab/configs/. It also returns a list of all
    switches in {hostname}_{system_mac} format and a list of all links interconnecting 
    the switches. Only links between two devices in the switch list are mapped."""
    switch_db = {} # Temp dictionary used to build endpoint link list.

    # Iterate over each switch passed into the switch_list.
    for switch in switch_list:
        # Setup API connection for the switch
        connection = pyeapi.connect(host=switch.rstrip(), transport='https', username=api_user, password=api_password)
        
        # Set usable siphers
        connection.transport._context.set_ciphers('DHE-RSA-AES256-SHA')
        
        # Get hostname and system mac 
        output = connection.execute(['enable', 'show hostname', 'show version'])

        # Format and assign to variables for easier reference
        hostname = output['result'][1]['hostname']
        system_mac = output['result'][2]['systemMacAddress'].replace(':','')

        # Get the running config.
        output = connection.execute(['enable', 'show running-config'], 'text')

        # Save the running config to the clab/configs directory,
        with open(f"clab/configs/{hostname}_{system_mac}.cfg", "w") as config:
            config.write(output['result'][1]['output'])
        
        # Create dictionary in the switch_db dictionary for the lldp neighbors
        # info from the switch.
        switch_db[f'{hostname}_{system_mac}'] = {
            'host': f'{hostname}_{system_mac}',
            'interfaces': {}
        }
        
        # Get LLDP neighbor info for the switch.
        output = connection.execute(['enable', 'show lldp neighbors detail'])

        # Iterate over each interface that had LLDP information.
        for interface, neighbor_info in output['result'][1]['lldpNeighbors'].items():
            
            # Make sure management interface isn't mapped.
            if 'Man' not in interface:
                
                # Get the remote hostname from LLDP info.
                remote_hostname = neighbor_info['lldpNeighborInfo'][0]['systemName']
                
                # Get the remote chassis ID from LLDP info.
                remote_system_mac = neighbor_info['lldpNeighborInfo'][0]['chassisId'].replace('.','')
                
                # Create a dictionary for the interface in the switch dictionary.
                # (PS I really like nested dictionaries.)
                switch_db[f'{hostname}_{system_mac}']['interfaces'][interface] = {}
                
                # Add the remote host to the interface dictionary
                switch_db[f'{hostname}_{system_mac}']['interfaces'][interface]['remote_host'] = f'{remote_hostname}_{remote_system_mac}'
                
                # Add the remote interface to the interface dictionary
                remote_interface = neighbor_info['lldpNeighborInfo'][0]['neighborInterfaceInfo']['interfaceId_v2']
                switch_db[f'{hostname}_{system_mac}']['interfaces'][interface]['remote_interface'] = remote_interface

    # Temp list used to hold all the links between hosts
    temp_endpoint_list =  []

    # Iterate over each switch in the switch_db
    for host, host_info in switch_db.items():
        
        # Iterate over each interface for the switch/host.
        for interface, neighbor_info in host_info['interfaces'].items():
            
            # This checks the switch_db to see if the remote host and interface are in the 
            # switch_db. If so, both ends of the link have been mapped and the link should be 
            # added to the endpoint_list. If not the other device is most likely a server/host
            # on the network and should be ignored. Try and except is used to handle KeyErrors
            # that happen when you check the switch_db for remote hosts that weren't mapped.
            try: 
                if neighbor_info["remote_interface"] in switch_db[neighbor_info["remote_host"]]['interfaces']:
                    local_interface = f'{host}:{interface.replace("Ethernet","et")}'
                    remote_interface = f'{neighbor_info["remote_host"]}:{neighbor_info["remote_interface"].replace("Ethernet","et")}'
                    temp_endpoint_list.append((local_interface,remote_interface))
            except KeyError:
                pass

    # The temp_endpoint_list ends up having duplicate links since it maps each link from 
    # both switches. Its easier to do that and then remove the duplicates by sorting
    # the list and converting it to a set than to have logic that makes sure all appropriate
    # links are added without having duplicates.
    endpoint_list = set(tuple(sorted(endpoint)) for endpoint in temp_endpoint_list)
    
    # The list of switches needs to be in an ordered list so they can be passed to both
    # jinja2 templates in the same order so assigned IP addresses are the same in both 
    # templates.
    node_list = list(switch_db.keys())
    
    return endpoint_list, node_list

def render_templates(endpoints, nodes):
    """This function creates a containerlab topology template from the data collected in the 
    map_network function. It also creates an override config for each switch. The override
    config is applied after the saved config on each switch. This allows for anything in the 
    config that need to be changed between a production and lab environment. for instance 
    disabling AAA, adding a local user, and setting the management interface for the lab 
    network"""
    
    # Values pass to the templates.
    kwargs = {
        'endpoints': endpoints,
        'nodes': nodes
    }

    # Jinja2 setup
    templateLoader = jinja2.FileSystemLoader(searchpath="templates/")
    templateEnv = jinja2.Environment(loader=templateLoader)
    
    # Get the container lab topology template.
    template_file = "topology.jinja2"
    template = templateEnv.get_template(template_file)
    
    # Render the template
    output = template.render(**kwargs)  

    # Save the template to the clab/ directory
    with open("clab/topology.yml", "w") as topology:
        topology.write(output)

    # Get the override_config template/
    template_file = "override_config.jinja2"
    template = templateEnv.get_template(template_file)
    
    # Iterate over each switch in the node list. Set the index to be non zero
    # based to match the jinja loop logic used in the topology template so each
    # node will have the same IP address in both files.
    for index, node in enumerate(nodes,start=1):
        
        # Values passed into the template.
        kwargs = {
            'index': index,
            'node': node
        }

        # Render the template
        output = template.render(**kwargs)  

        # Save the override_config file to  clab/override)configs directory.
        with open(f"clab/override_configs/{node}.cfg", "w") as override_config:
            override_config.write(output)

# Boilerplate to make this an importable module. 
if __name__ == "__main__":
    
    # Load the config.
    config  = load_config()
    
    # Map the network.
    endpoints, nodes = map_network(config['api_user'],config['api_password'],config['switch_list'])
    
    # Generate the files.
    render_templates(endpoints, nodes)

    # That's it. You're done. Start the topology in containerlab and go get a cup of 
    # tea while the copy of your network boots up in a lab environment for testing. 
