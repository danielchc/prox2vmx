
#  prox2vmx
####  🛠️ PVE to VMware Converter

This script converts a Proxmox Virtual Environment (PVE) VM into a VMware-compatible  `.vmx`  file and transforms the disk image (`.qcow2`  or  `.vmdk`) into a format compatible with VMware.

## 📦 Features

-   Converts PVE VM configuration to  `.vmx`
-   Converts disk image to VMware-compatible  `.vmdk`
-   Optionally preserves the original MAC address
- 
## 📥 Download

To download the script, use the following command (replace the placeholder with the actual URL):

```bash
curl  -O  <URL_TO_SCRIPT>
```
  

## 🚀 Usage

```bash
python3 prox2vmx.py  <vm_id>  [--preserve-mac]
```


### Arguments

-   `<vm_id>`: ID of the VM to convert (required)
-   `--preserve-mac`: Optional flag to preserve the original MAC address in the  `.vmx`  file

### Example

```bash
python3 prox2vmx.py 101
```
 

## 📁 Requirements

-   Must be executed on the server where the VM configuration and disk are stored
-   Ensure the VM is powered off before running the script.

## 📂 Output

-   A  `.vmx`  file generated from the VM configuration
-   A converted  `.vmdk`  disk image compatible with VMware
-  This `.vmx` can be registered in ESXi host or vCenter 
