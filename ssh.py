import paramiko
import re
from model import db, Router, Interface

# hostname = {'R1': '192.168.1.1',
#             'R2': '192.168.2.1',
#             'R3': '192.168.3.1'}
username = 'quagga'
key_path = '/home/manager/.ssh/authorized_keys'

def get_router_info():
    routers_info = {}
    routers = Router.query.all()
    for router in routers:
        interfaces = Interface.query.filter_by(router_id=router.id).all()
        ips = [iface.ip_address for iface in interfaces]
        if ips:
            routers_info[router.name] = ips[0]  
    return routers_info

def update_snmp_community_string(router_name, new_community_string):
    routers_info = get_router_info()
    if router_name not in routers_info:
        print(f"Router {router_name} not found in database.")
        return False

    hostname = routers_info[router_name]
    config_path = '/etc/snmp/snmpd.conf'
    
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname, username=username, key_filename=key_path)

        # Use sudo to read the configuration
        stdin, stdout, stderr = client.exec_command(f'sudo cat {config_path}')
        config_lines = stdout.readlines()
        
        if stderr.read():
            raise Exception(stderr.read().decode('utf-8'))

        # Update the community string
        new_config_lines = []
        community_string_pattern = re.compile(r'^\s*rwcommunity\s+\S+\s+\d+\.\d+\.\d+\.\d+\s*$')
        for line in config_lines:
            if community_string_pattern.match(line):
                new_config_lines.append(re.sub(r'rwcommunity\s+\S+', f'rwcommunity {new_community_string}', line))
            else:
                new_config_lines.append(line)

        # Write the new configuration back to the file using sudo
        temp_config_path = f'/tmp/snmpd.conf'
        with open(temp_config_path, 'w') as temp_config_file:
            temp_config_file.writelines(new_config_lines)

        sftp = client.open_sftp()
        sftp.put(temp_config_path, temp_config_path)
        sftp.close()

        stdin, stdout, stderr = client.exec_command(f'sudo mv {temp_config_path} {config_path}')
        if stderr.read():
            raise Exception(stderr.read().decode('utf-8'))

        # Restart the SNMP service to apply changes
        stdin, stdout, stderr = client.exec_command('sudo systemctl restart snmpd')
        stdout.channel.recv_exit_status()  # Wait for command to complete

        client.close()
        return True
    except Exception as e:
        print(f"Failed to update SNMP community string on {router_name}: {e}")
        return False