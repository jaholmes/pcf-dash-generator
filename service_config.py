import os
import time
from multiprocessing import Process

bind = "0.0.0.0:{port}".format(port=os.getenv('VCAP_APP_PORT', '5000'))
workers = 2
pythonpath = os.curdir

REFRESH_TIME_SECS = 300


def write_cert_file():
    if 'APPD_NOZZLE_CERT_FILE' in os.environ:
        open('cert.pem', 'w').write(os.getenv('APPD_NOZZLE_CERT_FILE'))
        print(os.path.abspath("cert.pem"))


def upload_hr_dashboard():
    import pcf_dash_generator
    pcf_dash_generator.logger.info("Generating Dash Board using a separate thread")
    while True:
        try:
            pcf_dash_generator.publish_dashboard_and_hrs(retry=True, hr_overwrite=False, dashboard_overwrite=True)
        except KeyError as kexc:
            pcf_dash_generator.logger.error('Key not found' + str(kexc))

        pcf_dash_generator.logger.info("Dashboard will be refreshed in {} seconds".format(REFRESH_TIME_SECS))
        time.sleep(REFRESH_TIME_SECS)
        pcf_dash_generator.logger.debug("Refreshing Dashboard and Health rules")


def when_ready(server):
    import pcf_dash_generator
    write_cert_file()
    bootstrap_worker = Process(target=upload_hr_dashboard)
    bootstrap_worker.start()
    pcf_dash_generator.logger.info("Dashboard Ready!")
