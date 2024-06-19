from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
import asyncio
from snmp_collector import collect_data
from ssh import update_snmp_community_string
from model import db, Router, Interface  

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///routers.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Data to be added initially
# COMMUNITY_STRINGS = {
#     'R1': {
#         'community': 'ex@mple1',
#         'ips': ['192.168.0.1', '192.168.1.1', '10.0.0.1']
#     },
#     'R2': {
#         'community': 'ex@mple2',
#         'ips': ['192.168.1.2', '192.168.2.1']
#     },
#     'R3': {
#         'community': 'ex@mple3',
#         'ips': ['192.168.2.2', '192.168.3.1', '10.0.0.2']
#     }
# }

# Create tables if they don't exist and add initial data
with app.app_context():
    db.create_all()
    # Add initial data
    # for router_name, details in COMMUNITY_STRINGS.items():
    #     router = Router.query.filter_by(name=router_name).first()
    #     if not router:
    #         router = Router(name=router_name, community_string=details['community'])
    #         db.session.add(router)
    #         db.session.commit()
    #         for ip in details['ips']:
    #             interface = Interface(ip_address=ip, router_id=router.id)
    #             db.session.add(interface)
    #         db.session.commit()

@app.route('/')
async def index():
    data = await collect_data()
    return render_template('index.html', data=data)

@app.route('/configuration', methods=['GET', 'POST'])
def configuration():
    if request.method == 'POST':
        router = request.form['router']
        new_community_string = request.form['community_string']
        success = update_snmp_community_string(router, new_community_string)
        if success:
            router_entry = Router.query.filter_by(name=router).first()
            if router_entry:
                router_entry.community_string = new_community_string
                db.session.commit()
            message = f"Successfully updated SNMP community string on {router} to {new_community_string}"
        else:
            message = f"Failed to update SNMP community string on {router}"
        return render_template('configuration.html', message=message)
    return render_template('configuration.html')


@app.route('/routers', methods=['GET'])
def manage_routers():
    routers = Router.query.all()
    return render_template('routers.html', routers=routers)

@app.route('/add_router', methods=['POST'])
def add_router():
    name = request.form['name']
    community_string = request.form['community_string']
    new_router = Router(name=name, community_string=community_string)
    db.session.add(new_router)
    db.session.commit()
    return redirect(url_for('manage_routers'))

@app.route('/add_interface/<int:router_id>', methods=['POST'])
def add_interface(router_id):
    ip_address = request.form['ip_address']
    new_interface = Interface(ip_address=ip_address, router_id=router_id)
    db.session.add(new_interface)
    db.session.commit()
    return redirect(url_for('manage_routers'))

@app.route('/edit_router/<int:router_id>', methods=['POST'])
def edit_router(router_id):
    router = Router.query.get_or_404(router_id)
    router.name = request.form['name']
    router.community_string = request.form['community_string']
    db.session.commit()
    return redirect(url_for('manage_routers'))

@app.route('/edit_interface/<int:interface_id>', methods=['POST'])
def edit_interface(interface_id):
    interface = Interface.query.get_or_404(interface_id)
    interface.ip_address = request.form['ip_address']
    db.session.commit()
    return redirect(url_for('manage_routers'))

@app.route('/delete_router/<int:router_id>', methods=['POST'])
def delete_router(router_id):
    router = Router.query.get_or_404(router_id)
    db.session.delete(router)
    db.session.commit()
    return redirect(url_for('manage_routers'))

@app.route('/delete_interface/<int:interface_id>', methods=['POST'])
def delete_interface(interface_id):
    interface = Interface.query.get_or_404(interface_id)
    db.session.delete(interface)
    db.session.commit()
    return redirect(url_for('manage_routers'))

@app.route('/visualization')
async def visualization():
    data = await collect_data()
    return render_template('visualization.html', data=data)

@app.route('/api/data')
async def api_data():
    data = await collect_data()
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)
