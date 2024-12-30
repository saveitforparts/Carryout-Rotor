import serial
import socket 
import regex as re
from typing import Tuple
from dataclasses import dataclass
import argparse

@dataclass
class AntennaPosition:
    """Stores the current position of the antenna"""
    azimuth: float = 0.0    # Horizontal rotation angle
    elevation: float = 0.0   # Vertical angle

class CarryoutController:
    """Controls the Winegard Carryout antenna hardware"""
    
    def __init__(self, port: str = '/dev/ttyUSB0', baudrate: int = 57600):
        """Sets up the serial connection to the antenna
        port: USB port where antenna is connected
        baudrate: Communication speed with antenna"""
        self.position = AntennaPosition()
        self.serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=1
        )
        self._initialize_connection()
    
    def _initialize_connection(self):
        """Resets antenna to root menu state for clean communication"""
        self.serial.write(bytes(b'q\r'))
        self.serial.write(bytes(b'\r'))
        
    def move_to_position(self, target_az: float, target_el: float) -> bool:
        """Commands antenna to move to specified position
        target_az: Target azimuth angle
        target_el: Target elevation angle
        Returns: True if position update successful"""
        self.serial.write(bytes(b'target\r'))
        command = f'g {target_az} {target_el}\r'.encode('ascii')
        self.serial.write(command)
        return self._update_current_position()
    
    def _update_current_position(self) -> bool:
        """Reads and parses current position from antenna
        Returns: True if position successfully parsed"""
        reply = self.serial.read(100).decode().strip()
        readings = reply.split(" ")
        readings = [re.sub('[^a-z0-9]+', '', r) for r in readings]
        
        try:
            el_index = readings.index("el")
            if el_index >= 3:
                self.position.azimuth = int(readings[el_index-3])/100
                self.position.elevation = int(readings[el_index+2][:4])/100
                return True
        except (ValueError, IndexError):
            return False
        return False

class GpredictInterface:
    """Handles network communication with Gpredict software"""
    
    def __init__(self, ip: str = '127.0.0.1', port: int = 4533):
        """Sets up network socket for Gpredict communication
        ip: IP address to listen on
        port: Port number for Gpredict connection"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((ip, port))
        self.socket.listen(1)
        print(f'Listening for rotor commands on {ip}:{port}')
        
    def accept_connection(self) -> Tuple[socket.socket, tuple]:
        """Waits for and accepts connection from Gpredict
        Returns: Connection socket and address tuple"""
        return self.socket.accept()

def main():
    """Main program loop that:
    1. Sets up command line arguments
    2. Initializes antenna and network connections
    3. Processes commands from Gpredict
    4. Handles cleanup on exit"""
    
    parser = argparse.ArgumentParser(description='Winegard Carryout Controller')
    parser.add_argument('--port', default='/dev/ttyUSB0', help='Serial port for antenna')
    parser.add_argument('--listen-port', type=int, default=4533, help='Port to listen for Gpredict')
    args = parser.parse_args()

    controller = CarryoutController(port=args.port)
    interface = GpredictInterface(port=args.listen_port)
    
    conn, addr = interface.accept_connection()
    print(f'Connection from {addr}')

    try:
        while True:
            data = conn.recv(100)
            if not data:
                break

            cmd = data.decode("utf-8").strip().split(" ")
            
            if cmd[0] == "p":  # Position request
                response = f"{controller.position.azimuth}\n{controller.position.elevation}\n"
                conn.send(response.encode('utf-8'))
                
            elif cmd[0] == "P":  # Move command
                target_az = float(cmd[1])
                target_el = float(cmd[2])
                print(f' Move antenna to: {target_az} {target_el}', end="\r")
                
                if controller.move_to_position(target_az, target_el):
                    conn.send("RPRT 0\n".encode('utf-8'))
                else:
                    conn.send("RPRT 1\n".encode('utf-8'))
                    
            elif cmd[0] == "S":  # Stop command
                raise KeyboardInterrupt
                
    except (KeyboardInterrupt, Exception) as e:
        print('\nShutting down...')
    finally:
        conn.close()
        controller.serial.close()

if __name__ == "__main__":
    main()
