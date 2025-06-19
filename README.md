# Battleship Game

A multiplayer online Battleship game implemented in Python using pygame for the client interface and socket programming for networking.

## Features

- **Multiplayer Online Gameplay**: Two players can connect and play against each other over a network
- **Classic Battleship Rules**: Standard 10x10 grid with traditional ship placement (Carrier, Battleship, Cruiser, Submarine, Destroyer)
- **Interactive GUI**: Pygame-based graphical interface with mouse controls
- **Real-time Communication**: Server-client architecture with JSON message protocol
- **Ship Placement**: Interactive ship placement with rotation support
- **Attack System**: Click-to-attack interface with visual feedback
- **Game State Management**: Turn-based gameplay with proper state synchronization

## Game Rules

### Ships
Each player places 5 ships on their 10x10 grid:
- **Carrier**: 5 cells
- **Battleship**: 4 cells  
- **Cruiser**: 3 cells
- **Submarine**: 3 cells
- **Destroyer**: 2 cells

### Gameplay
1. Players take turns attacking each other's boards
2. Click on the opponent's board to attack a cell
3. Hits are marked with 'X', misses with 'O'
4. When all cells of a ship are hit, the ship is sunk
5. First player to sink all opponent ships wins

## Installation

### Prerequisites
- Python 3.11 or higher
- pip package manager

### Setup
1. Clone or download the game files
2. Navigate to the game directory
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## How to Run

### Starting the Server
1. Open a terminal in the game directory
2. Run the server:
   ```bash
   python server.py
   ```
3. The server will start on `0.0.0.0:8888` and wait for connections

### Starting the Client
1. Open another terminal (or run on a different machine)
2. Run the client:
   ```bash
   python main.py
   ```
3. The client will automatically connect to `localhost:8888`

### For Network Play
To play over a network:
1. Start the server on one machine
2. Edit `main.py` and change the host in the `BattleshipClient()` initialization to the server's IP address
3. Run clients from other machines

## Game Controls

### Ship Placement Phase
- **Mouse Click**: Place ship at cursor position
- **R Key**: Rotate ship orientation (Horizontal/Vertical)
- Ships must be placed within the grid boundaries
- Ships cannot overlap

### Battle Phase  
- **Mouse Click**: Attack opponent's board
- Click on any cell in the opponent's grid to attack
- You can only attack on your turn
- Already attacked cells cannot be attacked again

## File Structure

```
battleship_game/
├── main.py              # Main client application with pygame GUI
├── server.py            # Game server handling multiplayer connections
├── client_network.py    # Network client class for server communication
├── game_logic.py        # Core game logic and rules
├── requirements.txt     # Python dependencies
├── README.md           # This documentation
└── bin/unused/         # Unused files from original project
```

## Technical Details

### Architecture
- **Server**: Multi-threaded TCP server handling multiple client connections
- **Client**: Pygame-based GUI with network communication thread
- **Protocol**: JSON messages over TCP sockets
- **Game Logic**: Separate module handling game rules and state

### Message Protocol
The game uses JSON messages for client-server communication:
- `join_game`: Request to join a game
- `place_ships`: Send ship placement data
- `attack`: Send attack coordinates
- `game_state`: Request current game state

### Network Configuration
- **Default Host**: `localhost` (127.0.0.1)
- **Default Port**: 8888
- **Protocol**: TCP
- **Message Format**: JSON over UTF-8 encoded strings

## Troubleshooting

### Common Issues

**"Failed to connect to server"**
- Ensure the server is running before starting clients
- Check that the host/port configuration matches
- Verify firewall settings allow connections on port 8888

**"Module not found: pygame"**
- Install pygame: `pip install pygame`
- Ensure you're using the correct Python version

**Game freezes during ship placement**
- Press 'R' to rotate ships if they don't fit
- Ensure ships don't overlap with existing ships
- Ships must be placed entirely within the 10x10 grid

**Network play doesn't work**
- Edit the host address in `main.py` to match the server's IP
- Ensure both machines can reach each other over the network
- Check firewall settings on both client and server machines

## Development

### Adding Features
The modular design makes it easy to extend:
- **Game Logic**: Modify `game_logic.py` for rule changes
- **UI**: Update `main.py` for interface improvements  
- **Networking**: Extend `server.py` and `client_network.py` for new features
- **Protocol**: Add new message types in the JSON protocol

### Testing
- Run `python game_logic.py` to test core game mechanics
- Run `python client_network.py` to test network connectivity
- Use multiple client instances to test multiplayer functionality

## License

This project is provided as-is for educational and entertainment purposes.

