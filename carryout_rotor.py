# Python program to control Winegard Carryout as an AZ/EL Rotor from Gpredict
# Version 1.0
# Gabe Emerson / Saveitforparts 2024, Email: gabe@saveitforparts.com

import socket

import regex as re
import serial

# initialize some variables
current_az = 0.0
current_el = 0.0
index = 0

# define "carryout" as the serial port device to interface with
carryout = serial.Serial(
    port="/dev/ttyUSB0",  # pass this from command line in future?
    baudrate=57600,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=1,
)

print("Carryout antenna connected on ", carryout.port)

carryout.write(b"q\r")  # go back to root menu in case firmware was left in a submenu
carryout.write(b"\r")  # clear firmware prompt to avoid unknown command errors


# listen to local port for rotctld commands
listen_ip = "127.0.0.1"  # listen on localhost
listen_port = 4533  # pass this from command line in future?
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.bind((listen_ip, listen_port))
client_socket.listen(1)

print(f"Listening for rotor commands on {listen_ip} : {listen_port}")
conn, addr = client_socket.accept()
print(f"Connection from {addr}")


# Would be nice to get initial / resting position from Carryout firmware
# I have not found a way to do this, just live position while motors are running


# pass rotor commands to Carryout
while 1:
    data = conn.recv(100)  # get Gpredict's message
    if not data:
        break

    cmd = data.decode("utf-8").strip().split(" ")  # grab the incoming command

    # print(f"Received: {cmd}")  #debugging, what did Gpredict send?

    if cmd[0] == "p":  # Gpredict is requesting current position
        response = f"{current_az}\n{current_el}\n"
        conn.send(response.encode("utf-8"))

    elif cmd[0] == "P":  # Gpredict is sending desired position
        target_az = float(cmd[1])
        target_el = float(cmd[2])
        print(f"Move antenna to: {target_az} {target_el}", end="\r")

        # tell Carryout to move to target position
        carryout.write(b"target\r")
        command = (f"g {target_az} {target_el}\r").encode("ascii")
        carryout.write(command)

        # read live position updates from Carryout
        reply = carryout.read(100).decode().strip()  # read dish response
        header, *readings = reply.split(" ")  # Split into list
        [re.sub("[^a-z0-9]+", "", _) for _ in readings]  # clean out garbage chars
        # print('Carryout replied:', readings)     #debugging

        # massage messy output into az/el
        while index < len(readings):
            if readings[index] == "el" and (index + 2) < len(readings):
                current_az = readings[index - 3]
                current_el = readings[index + 2]
                current_el = current_el[:4]  # strip off excess garbage
                current_az = int(current_az) / 100  # convert to format Gpredict expects
                current_el = int(current_el) / 100  # (Add the decimal)
                index += 1  # maybe unnecessary
                break
            else:
                index += 1
                continue

        # Tell Gpredict things went correctly
        response = "RPRT 0\n "  # Everything's under control, situation normal
        conn.send(response.encode("utf-8"))

        carryout.write(b"q\r")  # go back to Carryout's root menu

    elif cmd[0] == "S":  # Gpredict says to stop
        print(
            "Gpredict disconnected, exiting"
        )  # Do we want to do something else with this?
        conn.close()
        carryout.close()
        exit()
    else:
        print("Exiting")
        conn.close()
        carryout.close()
        exit()
