# pcf-dash-generator
- The Appd Tile will publish a platform dashboard and set of HRs to monitor key performance and scaling indicators for the PCF foundation that the tile is deployed to
- The HRs and dashboard leverage the metrics that the Appd tile collects from the Loggregator Firehose and publishes to the Appd application configured in the tile
- The key performance and scaling indicators monitored by the published dashboard and HRs are based on what Pivotal recommends and documents here:
https://docs.pivotal.io/pivotalcf/2-1/monitoring/index.html
- Screenhost of dashboards and HRs (todo)
- The HRs and dashboard are deployed to the controller and app entered in the tile.
- The user and password fields in the tile are used to create the HRs and dashboard via the REST API, and will require permissions to create dashboards and HRs in the target controller and app
 

- The dashboard will have the name <app name>-<tile name>-PCF KPI Dashboard
- The HRs will have the tier name prepended to the name. The HRs are created in the target application entered in the tile
- The dashboards and HRs are published via a PCF application that is deployed by the tile
- When the tile is deployed, the application will create the dashboard and HRs only if they don't already exist.
- The dashboards and HRs are based on a template that assumes a minimal PCF foundation where there is a single instance of each PCF service (controller, controller_worker, etc) and 3 instances of the diego_cell service.
- List services
- If the PCF foundation has a different number of instances for any service, the deployed dashboard and HRs can be modified to include the additional instances. For more information see the <github repo>. If there's a specific number of instances that are used repeatedly to deploy new PCF foundations, it's also possible to update the default platform dashboard and HR templates to support this.
