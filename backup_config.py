import pyeapi

connection = pyeapi.connect(host='172.100.100.101', transport='https', username='admin', password='admin')
connection.transport._context.set_ciphers('DHE-RSA-AES256-SHA')

output = connection.execute(['enable', 'show running-config'], 'text')

# print(output['result'][1]['output'])

with open("./project/configs/test.cfg", "x") as config:
    config.write(output['result'][1]['output'])
