"""
=================================================================
SECTION 2: DOCUMENTATION AND INSTALLATION GUIDE
=================================================================

# Satellite Tracking Control System

## Features
- Full antenna control (azimuth/elevation)
- Safety monitoring system
- Web interface for status and control
- Gpredict compatibility
- REST API for remote control
- Real-time position tracking

## Installation

### 1. System Requirements
- Python 3.8 or higher
- Linux/Unix system (tested on Ubuntu 20.04)
- USB port for antenna connection

### 2. Install Dependencies
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install requirements
pip install fastapi aiohttp pyserial pyyaml

### 3. Hardware Setup
Connect Winegard Carryout to USB port
Note the USB device path (usually /dev/ttyUSB0)
Ensure user has permission to access the USB port: sudo usermod -a -G dialout $USER
Running the System
Save this file as satellite_tracker.py
Run: python satellite_tracker.py
Access web interface: http://localhost:8080
Configure Gpredict to connect to localhost:4533
Operation Guide
System Start:

Start program
Wait for "System started successfully" message
Verify web interface accessibility
Manual Control:

Use web interface for direct control
Monitor safety parameters
Use emergency stop if needed
Gpredict Operation:

Select satellite in Gpredict
Enable rotator control
System will automatically track
Troubleshooting
Common Issues:

Connection Failed:

Check USB permissions
Verify correct port in settings
Ensure no other program is using the port
Movement Issues:

Check safety status in web interface
Verify position limits
Check motor temperatures
For additional support or feature requests:

Submit issues on GitHub
================================================================= """

