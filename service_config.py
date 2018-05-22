import os
from multiprocessing import Process

bind = "0.0.0.0:{port}".format(port=os.getenv('VCAP_APP_PORT', '5000'))
workers = 2
pythonpath = os.curdir


def write_cert_file():
    if 'APPD_NOZZLE_CERT_FILE' in os.environ:
        open('cert.pem', 'w').write(os.getenv('APPD_NOZZLE_CERT_FILE'))
        print(os.path.abspath("cert.pem"))


def when_ready(server):
    write_cert_file()
    import pcf_dash_generator
    pcf_dash_generator.logger.info("Generating Dash Board using a seperate thread")
    bootstrap_worker = Process(target=pcf_dash_generator.publish_dashboard_and_hrs, args=(True,))
    bootstrap_worker.start()
    pcf_dash_generator.logger.info("Finished.")
