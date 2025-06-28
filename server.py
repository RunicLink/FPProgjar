# battleship_server_http.py
import socket
import threading
import json
import uuid
import time
import logging
from battleship.game_logic import BattleshipGame

# --- Basic Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# We'll store all game states in memory. In a real production app, you'd use a database.
GAMES = {}
GAME_LOGIC = BattleshipGame()


# --- Main HTTP Server Class ---
class BattleshipHttpServer:
    """
    An HTTP server that handles the game logic for Battleship.
    It manages game creation, player turns, and game state via API endpoints.
    """

    def __init__(self):
        self.sessions = {}
        self.types = {
            '.pdf': 'application/pdf',
            '.jpg': 'image/jpeg',
            '.txt': 'text/plain',
            '.html': 'text/html'
        }

    def response(self, code=200, message='OK', body=None, headers={}):
        """Builds a complete HTTP response."""
        body_bytes = b''
        if body:
            if not isinstance(body, bytes):
                body_bytes = json.dumps(body).encode('utf-8')
            else:
                body_bytes = body
        
        final_headers = {
            "Content-Type": "application/json",
            "Server": "BattleshipHTTP/1.0",
            "Connection": "close",
        }
        final_headers.update(headers)
        final_headers["Content-Length"] = str(len(body_bytes))

        header_lines = [f"HTTP/1.0 {code} {message}"]
        for k, v in final_headers.items():
            header_lines.append(f"{k}: {v}")
        
        header_block = "\r\n".join(header_lines)
        return f"{header_block}\r\n\r\n".encode('utf-8') + body_bytes

    def get_headers_and_body(self, data):
        """Parses raw request data into headers and body."""
        try:
            parts = data.split('\r\n\r\n', 1)
            header_part = parts[0]
            body = parts[1] if len(parts) > 1 else ''
            headers = {}
            header_lines = header_part.split('\r\n')[1:]
            for line in header_lines:
                if ': ' in line:
                    key, value = line.split(': ', 1)
                    headers[key.lower()] = value
            return headers, body
        except Exception as e:
            logging.error(f"Error parsing headers and body: {e}")
            return {}, ''

    def process(self, data_str):
        """Processes an incoming raw HTTP request string."""
        try:
            request_line = data_str.split('\r\n')[0]
            parts = request_line.split(' ')
            method = parts[0].upper().strip()
            path = parts[1].strip()
            
            headers, body = self.get_headers_and_body(data_str)

            if method == 'GET':
                return self.http_get(path, headers)
            elif method == 'POST':
                return self.http_post(path, headers, body)
            else:
                return self.response(400, 'Bad Request', {'error': 'Unsupported method'})
        except Exception as e:
            logging.error(f"Error processing request: {e}")
            return self.response(500, 'Internal Server Error', {'error': 'Failed to process request'})

    def http_get(self, path, headers):
        """Handles GET requests, primarily for polling game state."""
        if path.startswith('/api/gamestate'):
            params = {}
            if '?' in path:
                query_string = path.split('?')[1]
                try:
                    params = dict(qc.split("=") for qc in query_string.split("&"))
                except ValueError:
                    return self.response(400, 'Bad Request', {'error': 'Malformed query string'})

            game_id = params.get('game_id')
            player_number = int(params.get('player_number', 0))

            if not game_id or game_id not in GAMES:
                return self.response(404, 'Not Found', {'error': 'Game not found'})
            
            game = GAMES[game_id]
            opponent_number = 2 if player_number == 1 else 1

            # Prepare a tailored game state for the requesting player
            state_for_player = {
                'type': 'game_state',
                'game_phase': game['phase'],
                'your_turn': game['turn'] == player_number and game['phase'] == 'playing',
                'own_board': game['player_boards'][player_number],
                'opponent_board': self.get_opponent_view(game['player_boards'][opponent_number]),
                'player_name': game['players'].get(player_number, {}).get('name'),
                'opponent_name': game['players'].get(opponent_number, {}).get('name'),
                'current_turn_player_name': game['players'].get(game['turn'], {}).get('name'),
                'status_message': game['status_message'],
                'game_over': game['phase'] == 'game_over',
                'winner': game.get('winner_name')
            }
            return self.response(200, 'OK', state_for_player)
        
        return self.response(404, 'Not Found', {'error': 'Endpoint not found'})
    
    def get_opponent_view(self, real_board):
        """Creates a view of the opponent's board, hiding un-hit ships."""
        view_board = [['.' for _ in range(10)] for _ in range(10)]
        for r in range(10):
            for c in range(10):
                if real_board[r][c] in ['X', 'O']:
                    view_board[r][c] = real_board[r][c]
        return view_board

    def http_post(self, path, headers, body):
        """Handles POST requests for game actions."""
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return self.response(400, 'Bad Request', {'error': 'Invalid JSON in request body'})

        if path == '/api/host':
            player_name = payload.get('player_name', 'Player 1')
            game_id = str(uuid.uuid4())[:8] # Short and sweet
            GAMES[game_id] = {
                'game_id': game_id,
                'players': {1: {'name': player_name, 'ships_placed': False}},
                'player_boards': {1: GAME_LOGIC.player1_board, 2: GAME_LOGIC.player2_board},
                'player_ships': {1: {}, 2: {}},
                'turn': 1,
                'phase': 'waiting_room', # waiting_room -> placing_ships -> playing -> game_over
                'status_message': 'Waiting for opponent to join...'
            }
            logging.info(f"Game {game_id} hosted by {player_name}")
            return self.response(200, 'OK', {'game_id': game_id, 'player_number': 1})

        game_id = payload.get('game_id')
        if not game_id or game_id not in GAMES:
            return self.response(404, 'Not Found', {'error': 'Game not found'})
        
        game = GAMES[game_id]
        player_number = payload.get('player_number')

        if path == '/api/join':
            if len(game['players']) >= 2:
                return self.response(403, 'Forbidden', {'error': 'Game is full'})
            player_name = payload.get('player_name', 'Player 2')
            game['players'][2] = {'name': player_name, 'ships_placed': False}
            game['phase'] = 'placing_ships'
            game['status_message'] = f"{player_name} has joined! Place your ships."
            logging.info(f"{player_name} joined game {game_id}")
            return self.response(200, 'OK', {'game_id': game_id, 'player_number': 2})
            
        if path == '/api/place_ships':
            if not player_number or game['phase'] != 'placing_ships':
                return self.response(400, 'Bad Request', {'error': 'Not in ship placement phase'})
            
            ships = payload.get('ships', [])
            board = [['.' for _ in range(10)] for _ in range(10)]
            ships_map = {}
            for ship_data in ships:
                # Using game_logic to validate and place ships
                GAME_LOGIC.place_ship(board, ships_map, ship_data['name'], GAME_LOGIC.ships[ship_data['name']], ship_data['start_row'], ship_data['start_col'], ship_data['orientation'])
            
            game['player_boards'][player_number] = board
            game['player_ships'][player_number] = ships_map
            game['players'][player_number]['ships_placed'] = True
            logging.info(f"Player {player_number} in game {game_id} placed ships.")

            # Check if both players have placed ships
            if all(p.get('ships_placed') for p in game['players'].values()):
                game['phase'] = 'playing'
                game['status_message'] = f"Game on! It's {game['players'][1]['name']}'s turn."
                logging.info(f"Game {game_id} starting.")

            return self.response(200, 'OK', {'message': 'Ships placed successfully'})

        if path == '/api/attack':
            if game['phase'] != 'playing' or player_number != game['turn']:
                return self.response(403, 'Forbidden', {'error': 'Not your turn or game not active'})
            
            row, col = payload.get('row'), payload.get('col')
            opponent_number = 2 if player_number == 1 else 1
            opponent_board = game['player_boards'][opponent_number]
            opponent_ships = game['player_ships'][opponent_number]

            result = GAME_LOGIC.attack(opponent_board, opponent_ships, row, col)
            game['status_message'] = f"Player {player_number} attacked ({row},{col}): {result}"
            logging.info(f"Game {game_id}: Player {player_number} attacks ({row},{col}). Result: {result}")

            if GAME_LOGIC.check_game_over(opponent_board, opponent_ships):
                game['phase'] = 'game_over'
                game['winner_name'] = game['players'][player_number]['name']
                game['status_message'] = f"Game Over! {game['winner_name']} wins!"
                logging.info(f"Game {game_id} over. Winner: {game['winner_name']}")
            else:
                # Switch turn
                game['turn'] = opponent_number
                game['status_message'] = f"It's {game['players'][opponent_number]['name']}'s turn."

            return self.response(200, 'OK', {'result': result})

        return self.response(404, 'Not Found', {'error': 'API endpoint not found'})


# --- Threading and Socket Server ---
# This section is from your server_thread_http.py, adapted for robustness.
httpserver = BattleshipHttpServer()

class ProcessTheClient(threading.Thread):
    def __init__(self, connection, address):
        self.connection = connection
        self.address = address
        threading.Thread.__init__(self)

    def run(self):
        request_data = b''
        # Read the entire request
        try:
            # Set a timeout to prevent blocking forever on a bad request
            self.connection.settimeout(1)
            while True:
                chunk = self.connection.recv(4096)
                if not chunk:
                    break
                request_data += chunk
                # Simple check for end of headers. A more robust server would parse Content-Length.
                if b'\r\n\r\n' in request_data:
                    break
        except socket.timeout:
            pass # Client sent partial data or is slow
        except Exception as e:
            logging.error(f"Error receiving data: {e}")
        
        if request_data:
            request_str = request_data.decode('utf-8')
            logging.info(f"Request from {self.address}:\n--- START ---\n{request_str}\n--- END ---")
            response_bytes = httpserver.process(request_str)
            self.connection.sendall(response_bytes)
        
        self.connection.close()


class Server(threading.Thread):
    def __init__(self, port=8889):
        self.port = port
        self.the_clients = []
        self.my_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        threading.Thread.__init__(self)

    def run(self):
        self.my_socket.bind(('0.0.0.0', self.port))
        self.my_socket.listen(5)
        logging.info(f"Battleship HTTP Server started on port {self.port}...")
        while True:
            try:
                connection, client_address = self.my_socket.accept()
                logging.info(f"Accepted connection from {client_address}")
                clt = ProcessTheClient(connection, client_address)
                clt.start()
                self.the_clients.append(clt)
            except Exception as e:
                logging.error(f"Error accepting connections: {e}")


def main():
    svr = Server()
    svr.start()

if __name__ == "__main__":
    main()