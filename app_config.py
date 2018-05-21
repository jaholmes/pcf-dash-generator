controller_url = None
account_name = None
user_name = None
user_pass = None
app = None
tier = None
tier_id = None
overwrite = False
start_service = None
port = None
commandline = False


def get_full_user_name():
    return user_name + '@' + account_name


def get_controller_url(host, port, ssl_enabled):
    controller_url = ''
    if ssl_enabled is True: 
        controller_url = 'https://' 
    else:
        controller_url = 'http://'
    controller_url += host
    if port is not None: controller_url += ':' + port
    return controller_url
