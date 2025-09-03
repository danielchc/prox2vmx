#!/usr/bin/python3
from datetime import datetime
import os
import re
import sys
import subprocess
import string
import random
import argparse


CONF_DIR = "/etc/pve/qemu-server"
GUESTOS_MAP = {
    "win11": "windows2019srvNext-64",
    "win10": "windows2019srv-64",
    "win8": "windows8srv-64",
    "win7": "windows7srv-64",
    "w2k8": "longhorn-64",
    "wxp": "winNetEnterprise-64",
    "l26": "otherlinux-64",
    "l24": "other24xlinux-64",
}


def random_name():
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=8))


def convert_disk_file(pve_path, vmdk_path):
    """Convert to vmdk using qemu-img"""

    disk_path = subprocess.run(
        ["pvesm", "path", pve_path], check=True, capture_output=True, text=True
    ).stdout.strip()

    if not os.path.exists(disk_path):
        print(f"Warning: {disk_path} not found, skipping conversion")
        return None

    print(f"Converting {pve_path} → {os.path.basename(vmdk_path)}")
    command = [
        "qemu-img",
        "convert",
        "-p",
        "-O",
        "vmdk",
        "-o",
        "adapter_type=lsilogic,subformat=monolithicFlat,compat6",
        disk_path,
        vmdk_path,
    ]
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    current_progress = ""
    while process.poll() is None:
        v = process.stdout.read(1)
        if v == b"\r":
            print(f"Progress: {current_progress.strip()}", end="\r")
            current_progress = ""
        else:
            current_progress += v.decode()

    process.stdout.read()
    process.stdout.close()

    return os.path.basename(vmdk_path)


def check_vm_is_running(vm_id):
    vm_status = subprocess.run(
        ["qm", "status", str(vm_id)], check=True, capture_output=True, text=True
    ).stdout.strip()
    return not ("stopped" in vm_status)


def parse_conf(filepath):
    """Parse Proxmox .conf into a dict"""
    cfg = {}
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            cfg[key.strip()] = value.strip()
    return cfg


def process_conf(cfg, preserve_mac=True):
    convert_tasks = []
    vmx_cfg = {}
    vm_name = cfg.get("name", "")

    vmx_cfg[".encoding"] = "UTF-8"
    vmx_cfg["displayName"] = vm_name
    vmx_cfg["numvcpus"] = cfg.get("cores", "1")
    vmx_cfg["memsize"] = cfg.get("memory", "4096")
    vmx_cfg["guestOS"] = GUESTOS_MAP.get(cfg.get("ostype", ""), "other-64")
    vmx_cfg["tools.syncTime"] = "TRUE"
    vmx_cfg["virtualHW.version"] = "19"
    vmx_cfg["config.version"] = "8"

    if cfg.get("bios") == "ovmf" or "efidisk0" in cfg:
        vmx_cfg["firmware"] = "efi"
        vmx_cfg["efi.present"] = "TRUE"

    if "smbios1" in cfg and "uuid=" in cfg["smbios1"]:
        uuid = cfg["smbios1"].split("uuid=")[1]
        vmx_cfg["uuid.bios"] = uuid

    disk_id = {"sata0": 0, "scsi0": 0}

    for key, entry in cfg.items():
        if re.match(r"^(sata|scsi|efidisk)\d", key):
            if entry.startswith("none,media=cdrom"):
                continue

            dev = "sata0"
            if re.match(r"^scsi\d", key):
                dev = "scsi0"
                vmx_cfg["scsi0.virtualDev"] = "lsilogic"

            vmx_cfg[f"{dev}.present"] = "TRUE"

            path = entry.split(",")[0]
            file = entry.split(",")[0]

            vmdk_name = f"{vm_name}-{dev}-disk-{disk_id[dev]}.vmdk"

            if ".qcow2" in entry or ".vmdk" in entry or ".raw" in entry:
                convert_tasks.append({"disk_file": file, "vmdk_name": vmdk_name})

            vmx_cfg[f"{dev}:{disk_id[dev]}.present"] = "TRUE"
            vmx_cfg[f"{dev}:{disk_id[dev]}.fileName"] = vmdk_name
            disk_id[dev] += 1

        if re.match(r"^net\d", key):
            nic_id = int("".join(ch for ch in key if ch.isdigit()))
            m = re.search(r"(?:virtio|e1000|e1000e|vmxnet3|rtl8139)=([^,]+)", entry)
            n = re.search(r"bridge=([^,]+)", entry)

            vmx_cfg[f"ethernet{nic_id}.addressType"] = "vpx"
            vmx_cfg[f"ethernet{nic_id}.present"] = "TRUE"
            vmx_cfg[f"ethernet{nic_id}.networkName"] = n.group(1) if n else "unknown"

            if preserve_mac:
                vmx_cfg[f"ethernet{nic_id}.address"] = m.group(1) if m else ""
                vmx_cfg[f"ethernet{nic_id}.addressType"] = "static"

    return vmx_cfg, convert_tasks


def generate_vmx(vmx_cfg, output_path):
    with open(output_path, "w") as f:
        for k, v in vmx_cfg.items():
            f.write(f'{k} = "{v}"\n')


def main():
    now = datetime.now().strftime("%Y-%m-%d_%H%M")

    parser = argparse.ArgumentParser(description="Convert PVE VM config to VMX format")
    parser.add_argument("vm_id", type=int, help="ID of the VM to convert")
    parser.add_argument(
        "--preserve-mac",
        action="store_true",
        help="Preserve the original MAC address in the VMX file",
    )

    args = parser.parse_args()

    vm_id = args.vm_id
    preserve_mac = args.preserve_mac

    conf_path = os.path.join(CONF_DIR, f"{vm_id}.conf")
    if not os.path.exists(conf_path):
        print(f"Error: {conf_path} does not exist.")
        sys.exit(1)

    cfg = parse_conf(conf_path)
    cfg["name"] = cfg.get("name", f"vm-{vm_id}-{random_name()}")
    vm_name = cfg["name"]
    out_dir = f"{vm_name}_{now}"

    if check_vm_is_running(vm_id):
        print(f"{vm_name} is currently running. You must stop it to be converted")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)

    print(f"Starting conversion {vm_name}")

    vmx_cfg, convert_tasks = process_conf(cfg, preserve_mac)

    for task in convert_tasks:
        convert_disk_file(task["disk_file"], os.path.join(out_dir, task["vmdk_name"]))

    generate_vmx(vmx_cfg, os.path.join(out_dir, f"{vm_name}.vmx"))

    print(f"\033[92mConversion successful: {vm_name}\033[0m")


if __name__ == "__main__":
    main()
