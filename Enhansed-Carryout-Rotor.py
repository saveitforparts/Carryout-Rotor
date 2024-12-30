# === config/config.yaml ===
"""
antenna:
  default_port: '/dev/ttyUSB0'
  default_baudrate: 57600
  retry_attempts: 3
  timeout: 1.0

network:
  host: '127.0.0.1'
  gpredict_port: 4533
  api_port: 8080

logging:
  level: INFO
  file: 'antenna.log'
"""

# === src/models/antenna.py ===
from dataclasses import dataclass
from typing import Optional

@dataclass
class AntennaPosition:
    azimuth: float = 0.0
    elevation: float = 0.0
    
    def validate(self) -> bool:
        return 0 <= self.azimuth <= 360 and 0 <= self.elevation <= 90

@dataclass
class AntennaStatus:
    position: AntennaPosition
    is_moving: bool = False
    error_state: Optional[str] = None
    last_command: Optional[str] = None

# === src/utils/exceptions.py ===
class AntennaControlError(Exception):
    """Base exception for antenna control errors"""
    pass

class CommunicationError(AntennaControlError):
    """Serial or network communication errors"""
    pass

class PositionError(AntennaControlError):
    """Invalid position or movement errors"""
    pass

class ConfigurationError(AntennaControlError):
    """Configuration related errors"""
    pass

# === src/utils/logging.py ===
import logging
import yaml
from pathlib import Path

def setup_logging():
    config_path = Path('config/config.yaml')
    with open(config_path) as f:
        config = yaml.safe_load(f)

    logging.basicConfig(
        level=config['logging']['level'],
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename=config['logging']['file']
    )
    
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger('').addHandler(console)

# === src/controllers/base_controller.py ===
from abc import ABC, abstractmethod

class BaseController(ABC):
    @abstractmethod
    def move_to_position(self, position: AntennaPosition) -> bool:
        pass
    
    @abstractmethod
    def get_status(self) -> AntennaStatus:
        pass
    
    @abstractmethod
    def stop(self) -> None:
        pass

# === src/controllers/carryout_controller.py ===
import serial
import regex as re
from typing import Optional

class CarryoutController(BaseController):
    def __init__(self, port: str, baudrate: int, retry_attempts: int = 3):
        self.logger = logging.getLogger(__name__)
        self.retry_attempts = retry_attempts
        self.status = AntennaStatus(position=AntennaPosition())
        
        try:
            self.serial = serial.Serial(
                port=port,
                baudrate=baudrate,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
                timeout=1
            )
            self._initialize_connection()
        except serial.SerialException as e:
            raise CommunicationError(f"Failed to initialize serial connection: {e}")

    def _initialize_connection(self):
        self.serial.write(bytes(b'q\r'))
        self.serial.write(bytes(b'\r'))
        self.logger.info(f"Initialized connection on {self.serial.port}")

    def move_to_position(self, position: AntennaPosition) -> bool:
        if not position.validate():
            raise PositionError("Invalid position requested")

        self.status.is_moving = True
        self.status.last_command = f"MOVE {position.azimuth} {position.elevation}"
        
        try:
            self.serial.write(bytes(b'target\r'))
            command = f'g {position.azimuth} {position.elevation}\r'.encode('ascii')
            self.serial.write(command)
            
            success = self._update_current_position()
            self.status.is_moving = False
            return success
            
        except serial.SerialException as e:
            self.status.error_state = str(e)
            self.logger.error(f"Movement error: {e}")
            raise CommunicationError(f"Failed to send movement command: {e}")

    def _update_current_position(self) -> bool:
        for attempt in range(self.retry_attempts):
            try:
                reply = self.serial.read(100).decode().strip()
                readings = reply.split(" ")
                readings = [re.sub('[^a-z0-9]+', '', r) for r in readings]
                
                el_index = readings.index("el")
                if el_index >= 3:
                    self.status.position.azimuth = int(readings[el_index-3])/100
                    self.status.position.elevation = int(readings[el_index+2][:4])/100
                    return True
                    
            except (ValueError, IndexError) as e:
                self.logger.warning(f"Position update attempt {attempt + 1} failed: {e}")
                continue
                
        self.status.error_state = "Failed to update position"
        return False

    def get_status(self) -> AntennaStatus:
        return self.status

    def stop(self) -> None:
        self.serial.write(bytes(b'q\r'))
        self.status.is_moving = False
        self.logger.info("Antenna movement stopped")

# === src/interfaces/gpredict_interface.py ===
import socket
from typing import Tuple, Optional

class GpredictInterface:
    def __init__(self, controller: BaseController, host: str, port: int):
        self.logger = logging.getLogger(__name__)
        self.controller = controller
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((host, port))
        self.socket.listen(1)
        self.logger.info(f'Listening for Gpredict commands on {host}:{port}')

    def handle_connection(self):
        conn, addr = self.socket.accept()
        self.logger.info(f'Connection from {addr}')

        try:
            while True:
                data = conn.recv(100)
                if not data:
                    break

                response = self._process_command(data.decode("utf-8").strip())
                if response:
                    conn.send(response.encode('utf-8'))

        except Exception as e:
            self.logger.error(f"Connection error: {e}")
        finally:
            conn.close()

    def _process_command(self, command: str) -> Optional[str]:
        cmd_parts = command.split(" ")
        cmd_type = cmd_parts[0]

        try:
            if cmd_type == "p":
                status = self.controller.get_status()
                return f"{status.position.azimuth}\n{status.position.elevation}\n"

            elif cmd_type == "P":
                position = AntennaPosition(
                    azimuth=float(cmd_parts[1]),
                    elevation=float(cmd_parts[2])
                )
                success = self.controller.move_to_position(position)
                return "RPRT 0\n" if success else "RPRT 1\n"

            elif cmd_type == "S":
                self.controller.stop()
                return "RPRT 0\n"

        except Exception as e:
            self.logger.error(f"Command processing error: {e}")
            return "RPRT 1\n"

# === src/interfaces/rest_api.py ===
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()

class RestAPI:
    def __init__(self, controller: BaseController):
        self.controller = controller
        
        @app.get("/status")
        async def get_status():
            return JSONResponse(content=self.controller.get_status().__dict__)
            
        @app.post("/move")
        async def move_antenna(position: AntennaPosition):
            try:
                success = self.controller.move_to_position(position)
                return {"success": success}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
                
        @app.post("/stop")
        async def stop_antenna():
            self.controller.stop()
            return {"success": True}

# === main.py ===
import yaml
import asyncio
import uvicorn
from pathlib import Path

def load_config():
    config_path = Path('config/config.yaml')
    with open(config_path) as f:
        return yaml.safe_load(f)

async def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    
    config = load_config()
    
    controller = CarryoutController(
        port=config['antenna']['default_port'],
        baudrate=config['antenna']['default_baudrate'],
        retry_attempts=config['antenna']['retry_attempts']
    )
    
    gpredict = GpredictInterface(
        controller=controller,
        host=config['network']['host'],
        port=config['network']['gpredict_port']
    )
    
    api = RestAPI(controller)
    
    try:
        gpredict_task = asyncio.create_task(
            asyncio.to_thread(gpredict.handle_connection)
        )
        
        config = uvicorn.Config(
            app=api.app,
            host=config['network']['host'],
            port=config['network']['api_port'],
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Error during execution: {e}")
    finally:
        controller.stop()

if __name__ == "__main__":
    asyncio.run(main())
