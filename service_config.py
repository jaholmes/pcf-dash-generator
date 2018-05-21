import os

bind = "0.0.0.0:{port}".format(port=os.getenv('VCAP_APP_PORT', '5000'))
workers = 2


def write_cert_file():
    if 'APPD_NOZZLE_CERT_FILE' in os.environ:
        open('cert.pem', 'w').write(os.getenv('APPD_NOZZLE_CERT_FILE'))
        print(os.path.abspath("cert.pem"))


def when_ready(server):
    write_cert_file()
