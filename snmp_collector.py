import asyncio
import time
import subprocess
from pysnmp.hlapi.asyncio import *
from model import db, Router, Interface  

INTERFACE_OID_IN = '1.3.6.1.2.1.2.2.1.10'
INTERFACE_OID_OUT = '1.3.6.1.2.1.2.2.1.16'
INTERFACE_OID_IN_ERRORS = '1.3.6.1.2.1.2.2.1.14'
INTERFACE_OID_OUT_ERRORS = '1.3.6.1.2.1.2.2.1.20'
INTERFACE_SPEED_OID = '1.3.6.1.2.1.2.2.1.5'
CPU_OID_USER = '1.3.6.1.4.1.2021.11.50.0'
CPU_OID_SYSTEM = '1.3.6.1.4.1.2021.11.52.0'
CPU_OID_IDLE = '1.3.6.1.4.1.2021.11.53.0'
MEMORY_OID_SIZE = '1.3.6.1.4.1.2021.4.5.0'
MEMORY_OID_USED = '1.3.6.1.4.1.2021.4.6.0'
ROUTER_STATUS_OID = '1.3.6.1.2.1.4.1.0'
OSPF_AREA_OID = '1.3.6.1.2.1.14.2.1.1'

last_poll_time = time.time()

def calculate_throughput(octets, elapsed_time):
    result = octets  / (elapsed_time * 1000)
    return float("{:.8f}".format(result))

def calculate_error_rate(errors, octets):
    result = (errors / octets) * 100 if octets != 0 else 0
    return float("{:.8f}".format(result))

def calculate_link_utilization(octets, elapsed_time, if_speed):
    result = (octets * 8 * 100) / (elapsed_time * if_speed)
    return float("{:.8f}".format(result))

async def get_snmp_data(credentials, oid):
    iterator = getCmd(
        SnmpEngine(),
        CommunityData(credentials['community'], mpModel=1),
        UdpTransportTarget((credentials['ip'], 161)),
        ContextData(),
        ObjectType(ObjectIdentity(oid))
    )
    errorIndication, errorStatus, errorIndex, varBinds = await iterator
    if errorIndication:
        return None
    elif errorStatus:
        return None
    else:
        for varBind in varBinds:
            return varBind[1]

async def walk_snmp_data(credentials, oid):
    iterator = walkCmd(
        SnmpEngine(),
        CommunityData(credentials['community'], mpModel=1),
        UdpTransportTarget((credentials['ip'], 161)),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
        lexicographicMode=False
    )
    errorIndication, errorStatus, errorIndex, varBinds = await iterator
    if errorIndication:
        return None
    elif errorStatus:
        return None
    else:
        return varBinds[1]
        
async def get_interface_data(credentials, index):
    in_oid = f"{INTERFACE_OID_IN}.{index}"
    out_oid = f"{INTERFACE_OID_OUT}.{index}"
    in_errors_oid = f"{INTERFACE_OID_IN_ERRORS}.{index}"
    out_errors_oid = f"{INTERFACE_OID_OUT_ERRORS}.{index}"
    if_speed_oid = f"{INTERFACE_SPEED_OID}.{index}"
    in_octets = await get_snmp_data(credentials, in_oid)
    out_octets = await get_snmp_data(credentials, out_oid)
    in_errors = await get_snmp_data(credentials, in_errors_oid)
    out_errors = await get_snmp_data(credentials, out_errors_oid)
    if_speed = await get_snmp_data(credentials, if_speed_oid)
    if in_octets is None or out_octets is None or in_errors is None or out_errors is None or if_speed is None:
        raise ValueError(f"Failed to retrieve SNMP data for {credentials['ip']} interface {index}")
    try:
        in_octets = int(in_octets)
        out_octets = int(out_octets)
        in_errors = int(in_errors)
        out_errors = int(out_errors)
        if_speed = int(if_speed)
    except (ValueError, TypeError):
        in_octets = 0
        out_octets = 0
        in_errors = 0
        out_errors = 0
        if_speed = 0
    return in_octets, out_octets, in_errors, out_errors, if_speed

async def get_cpu_usage(credentials):
    user_time = await get_snmp_data(credentials, CPU_OID_USER)
    system_time = await get_snmp_data(credentials, CPU_OID_SYSTEM)
    idle_time = await get_snmp_data(credentials, CPU_OID_IDLE)
    if user_time is None or system_time is None or idle_time is None:
        raise ValueError(f"Failed to retrieve SNMP data for {credentials['ip']}")
    try:
        user_time = int(user_time)
        system_time = int(system_time)
        idle_time = int(idle_time)
    except (ValueError, TypeError):
        user_time = 0
        system_time = 0
        idle_time = 0
    total_time = user_time + system_time + idle_time
    if total_time == 0:
        return "0.00%"
    cpu_usage = ((user_time + system_time) / total_time) * 100
    return "{:.2f}%".format(cpu_usage)

async def get_memory_usage(credentials):
    size = await get_snmp_data(credentials, MEMORY_OID_SIZE)
    used = await get_snmp_data(credentials, MEMORY_OID_USED)
    if size is None or used is None:
        raise ValueError(f"Failed to retrieve SNMP data for {credentials['ip']}")
    try:
        size = int(size)
        used = int(used)
    except (ValueError, TypeError):
        size = 1
        used = 0
    memory_usage = (used / size) * 100
    return "{:.2f}%".format(memory_usage)

async def is_router(credentials):
    status = await get_snmp_data(credentials, ROUTER_STATUS_OID)
    if status is None:
        raise ValueError(f"Failed to retrieve SNMP data for {credentials['ip']}")
    try:
        status = int(status)
    except (ValueError, TypeError):
        status = 2
    return status

def is_router_reachable(ip):
    try:
        subprocess.run(["ping", "-c", "1", ip], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError:
        return False

async def get_ospf_router_id(credentials):
    try:
        result = subprocess.run(
            ['snmpwalk', '-v2c', '-c', credentials['community'], credentials['ip'], '1.3.6.1.2.1.14.1.1'],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        output = result.stdout.decode('utf-8')
        router_id = output.split('=')[-1].strip().split(' ')[-1]
        return router_id
    except subprocess.CalledProcessError as e:
        print(f"Failed to retrieve OSPF Router ID for {credentials['ip']}: {e}")
        return None

async def collect_data():
    global last_poll_time
    data = {'routers': []}
    
    current_time = time.time()
    elapsed_time = current_time - last_poll_time
    last_poll_time = current_time

    routers = Router.query.all()
    for router in routers:
        interfaces = Interface.query.filter_by(router_id=router.id).all()
        router_data = {
            'name': router.name,
            'ips': [iface.ip_address for iface in interfaces],
            'traffic': {
                'inbound': [],
                'outbound': [],
                'in_errors': [],
                'out_errors': [],
                'response_times': [],
                'bandwidth_utilizations': [],
                'ospf_areas': []
            },
            'cpu': None,
            'memory': None,
            'router_status': None,
            'ospf_router_id': None,
            'status': 'inactive'
        }
        for iface in interfaces:
            ip = iface.ip_address
            if is_router_reachable(ip):
                router_data['status'] = 'active'
                credentials = {'community': router.community_string, 'ip': ip}
                try:
                    in_octets, out_octets, in_errors, out_errors, if_speed = await get_interface_data(credentials, interfaces.index(iface) + 1)
                    router_data['cpu'] = await get_cpu_usage(credentials)
                    router_data['memory'] = await get_memory_usage(credentials)
                    router_data['router_status'] = await is_router(credentials)
                    router_data['ospf_router_id'] = await get_ospf_router_id(credentials)

                    inbound_utilization = calculate_link_utilization(in_octets, elapsed_time, if_speed)
                    outbound_utilization = calculate_link_utilization(out_octets, elapsed_time, if_speed)
                    inbound_error_rate = calculate_error_rate(in_errors, in_octets)
                    outbound_error_rate = calculate_error_rate(out_errors, out_octets)

                    response_time = subprocess.run(
                        ["ping", "-c", "1", ip], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    ).stdout.decode().split('time=')[-1].split()[0] + ' ms'

                    max_utilization = max(inbound_utilization, outbound_utilization)
                    
                    router_data['traffic']['inbound'].append(inbound_utilization)
                    router_data['traffic']['outbound'].append(outbound_utilization)
                    router_data['traffic']['in_errors'].append(inbound_error_rate)
                    router_data['traffic']['out_errors'].append(outbound_error_rate)
                    router_data['traffic']['response_times'].append(response_time)
                    router_data['traffic']['bandwidth_utilizations'].append(max_utilization)
                except ValueError:
                    router_data['traffic']['inbound'].append(0)
                    router_data['traffic']['outbound'].append(0)
                    router_data['traffic']['in_errors'].append(0)
                    router_data['traffic']['out_errors'].append(0)
                    router_data['traffic']['response_times'].append("0 ms")
                    router_data['traffic']['bandwidth_utilizations'].append(0)
                    router_data['traffic']['ospf_areas'].append('N/A')
            else:
                router_data['traffic']['inbound'].append(0)
                router_data['traffic']['outbound'].append(0)
                router_data['traffic']['in_errors'].append(0)
                router_data['traffic']['out_errors'].append(0)
                router_data['traffic']['response_times'].append("0 ms")
                router_data['traffic']['bandwidth_utilizations'].append(0)
                router_data['traffic']['ospf_areas'].append('N/A')
        
        data['routers'].append(router_data)
    return data

if __name__ == '__main__':
    asyncio.run(collect_data())
