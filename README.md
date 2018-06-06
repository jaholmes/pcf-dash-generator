# pcf-dash-generator
## Overview
The PCF Dashboard Generator is a python 3 application that generates a platform dashboard and set of health rules for PCF foundations that have installed the Appd Tile 2.x (ref).
The generated dashboard and health rules leverage the custom metrics published by the Appd Tile to the AppD controller and application configured in the Appd Tile. These metrics are pulled from the PCF Loggregator Firehose and represent the core performance and scaling KPIs as documented by Pivotal here

## Dashboard
The dashboard is separated into 3 sections. The top section reflects the core capacity measurements and alerts for Diego Cell, Router and UAA services. The middle section lists performance alerts and a graph of Router throughput. The bottom section shows VM resource and health alerts for the core PCF services.

## Usage
The PCF Dashboard Generator can be run as a command line script or an application with a REST API. The Appd Tile installs the PCF Dashboard Generator as a PCF application, which is configured to automatically generate the dashboards and health rules at startup as part of the tile deployment.

## Dashboard and Health Rules Naming
The generated dashboard is named according to application and tier name configured in the Appd Tile, i.e. ${applicationName}-${tierName}-PCF KPI Dashboard.
The generated health rules are prefixed with the tier name configured in the tile, so that Appd Tiles deployed to multiple foundations can report to the same Appd application. An example is ${tierName}-Diego Cell Memory Capacity.

## Overwrite Behavior
The PCF Dashboard Generator will write the dashboard and health rules to the controller and application configured in the Appd Tile only if they do not exist. If you wish to recreate the dashboard  and overwrite the existing health rules you can rename or delete the existing ones, or if you're using the command line option, supply the appropriate overwrite/recreate flag.

## Adjusting Diego Cell Capacity Widgets and Health Rules
The dashboard and health rules are based on a template that assumes 3 Diego Cell VMs. If your foundation has a different number of Diego Cells, it will be necessary to edit the dashboard widgets and health rules related to Diego Cell capacity to properly reflect the actual capacity.
