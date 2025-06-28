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

# We'll store all game states in memory.
GAMES = {}
GAME_LOGIC = BattleshipGame()
TURN_TIMEOUT = 60  # 60 seconds per turn
CLIENT_INACTIVITY_TIMEOUT = 30 # 30 seconds of inactivity before marking as disconnected

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
            player_number_str = params.get('player_number')
            if not player_number_str:
                return self.response(400, 'Bad Request', {'error': 'Player number is required'})

            player_number = int(player_number_str)

            if not game_id or game_id not in GAMES:
                return self.response(404, 'Not Found', {'error': 'Game not found'})
            
            game = GAMES[game_id]

            if player_number in game['players']:
                game['players'][player_number]['last_activity'] = time.time()

            opponent_number = 2 if player_number == 1 else 1

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
                'winner': game.get('winner_name'),
                'turn_time_remaining': max(0, TURN_TIMEOUT - (time.time() - game.get('turn_start_time', 0))) if game['phase'] == 'playing' else None,
                'opponent_connected': game['players'].get(opponent_number, {}).get('connected', False),
                'own_sunk_ships': game['sunk_ships'][player_number],
                'opponent_sunk_ships': game['sunk_ships'][opponent_number],
                'placed_ships': game['players'].get(player_number, {}).get('placed_ships_data', [])
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
            return self.handle_host(payload)

        # *** FIX: Consolidate join and reconnect logic ***
        if path == '/api/reconnect' or path == '/api/join':
            return self.handle_join_or_reconnect(payload)
            
        game_id = payload.get('game_id')
        if not game_id or game_id not in GAMES:
            return self.response(404, 'Not Found', {'error': 'Game not found'})
        
        if path == '/api/place_ships':
            return self.handle_place_ships(payload, GAMES[game_id])

        if path == '/api/attack':
            return self.handle_attack(payload, GAMES[game_id])

        return self.response(404, 'Not Found', {'error': 'API endpoint not found'})

    def handle_host(self, payload):
        player_name = payload.get('player_name', 'Player 1')
        game_id = str(uuid.uuid4())[:8]
        GAMES[game_id] = {
            'game_id': game_id,
            'players': {1: {'name': player_name, 'ships_placed': False, 'connected': True, 'last_activity': time.time(), 'placed_ships_data': []}},
            'player_boards': {1: [['.' for _ in range(10)] for _ in range(10)], 2: [['.' for _ in range(10)] for _ in range(10)]},
            'player_ships': {1: {}, 2: {}},
            'sunk_ships': {1: [], 2: []},
            'turn': 1,
            'phase': 'waiting_room',
            'status_message': 'Waiting for opponent to join...',
            'turn_start_time': 0,
        }
        logging.info(f"Game {game_id} hosted by {player_name}")
        return self.response(200, 'OK', {'game_id': game_id, 'player_number': 1})

    def handle_join_or_reconnect(self, payload):
        game_id = payload.get('game_id')
        player_name = payload.get('player_name')

        if not game_id or game_id not in GAMES:
            return self.response(404, 'Not Found', {'error': 'Game not found'})
        if not player_name:
            return self.response(400, 'Bad Request', {'error': 'Player name is required'})
        
        game = GAMES[game_id]
        
        # Check if player is reconnecting
        reconnecting_player_number = None
        for p_num, p_data in game['players'].items():
            if p_data['name'] == player_name:
                reconnecting_player_number = p_num
                break

        if reconnecting_player_number:
            # This is a reconnect attempt for an existing player
            if game['players'][reconnecting_player_number]['connected']:
                return self.response(403, 'Forbidden', {'error': 'Player is already connected to this game.'})
            
            game['players'][reconnecting_player_number]['connected'] = True
            game['players'][reconnecting_player_number]['last_activity'] = time.time()
            logging.info(f"Player {player_name} reconnected to game {game_id} as player {reconnecting_player_number}")
            return self.response(200, 'OK', {'game_id': game_id, 'player_number': reconnecting_player_number, 'reconnected': True})
        else:
            # This is a new player joining
            if len(game['players']) >= 2:
                return self.response(403, 'Forbidden', {'error': 'Game is full'})
            
            player_number = 2
            game['players'][player_number] = {'name': player_name, 'ships_placed': False, 'connected': True, 'last_activity': time.time(), 'placed_ships_data': []}
            game['phase'] = 'placing_ships'
            game['status_message'] = f"{player_name} has joined! Place your ships."
            logging.info(f"{player_name} joined game {game_id} as player {player_number}")
            return self.response(200, 'OK', {'game_id': game_id, 'player_number': player_number})

    def handle_place_ships(self, payload, game):
        player_number = payload.get('player_number')
        if not player_number or game['phase'] != 'placing_ships':
            return self.response(400, 'Bad Request', {'error': 'Not in ship placement phase'})
        
        ships = payload.get('ships', [])
        board = [['.' for _ in range(10)] for _ in range(10)]
        ships_map = {}
        for ship_data in ships:
            GAME_LOGIC.place_ship(board, ships_map, ship_data['name'], GAME_LOGIC.ships[ship_data['name']], ship_data['start_row'], ship_data['start_col'], ship_data['orientation'])
        
        game['player_boards'][player_number] = board
        game['player_ships'][player_number] = ships_map
        game['players'][player_number]['ships_placed'] = True
        game['players'][player_number]['placed_ships_data'] = ships
        logging.info(f"Player {player_number} in game {game['game_id']} placed ships.")

        if len(game['players']) == 2 and all(p.get('ships_placed') for p in game['players'].values()):
            game['phase'] = 'playing'
            game['turn_start_time'] = time.time()
            game['status_message'] = f"Game on! It's {game['players'][1]['name']}'s turn."
            logging.info(f"Game {game['game_id']} starting.")

        return self.response(200, 'OK', {'message': 'Ships placed successfully'})

    def handle_attack(self, payload, game):
        player_number = payload.get('player_number')
        if game['phase'] != 'playing' or player_number != game['turn']:
            return self.response(403, 'Forbidden', {'error': 'Not your turn or game not active'})
        
        row, col = payload.get('row'), payload.get('col')
        opponent_number = 2 if player_number == 1 else 1
        opponent_board = game['player_boards'][opponent_number]
        opponent_ships = game['player_ships'][opponent_number]

        result = GAME_LOGIC.attack(opponent_board, opponent_ships, row, col)
        game['status_message'] = f"{game['players'][player_number]['name']} attacked ({row},{col}): {result}"
        logging.info(f"Game {game['game_id']}: Player {player_number} attacks ({row},{col}). Result: {result}")

        if "sunk" in result:
            sunk_ship_name = result.split("sunk ")[1].strip('!')
            if sunk_ship_name not in game['sunk_ships'][opponent_number]:
                game['sunk_ships'][opponent_number].append(sunk_ship_name)

        if GAME_LOGIC.check_game_over(opponent_ships):
            game['phase'] = 'game_over'
            game['winner_name'] = game['players'][player_number]['name']
            game['status_message'] = f"Game Over! {game['winner_name']} wins!"
            logging.info(f"Game {game['game_id']} over. Winner: {game['winner_name']}")
        else:
            game['turn'] = opponent_number
            game['turn_start_time'] = time.time()
            game['status_message'] = f"It's {game['players'][opponent_number]['name']}'s turn."

        return self.response(200, 'OK', {'result': result})


def game_housekeeping():
    """
    A background thread to manage game state, like turn timeouts and disconnections.
    """
    while True:
        games_to_remove = []
        for game_id, game in list(GAMES.items()):
            if game['phase'] == 'game_over' and time.time() - game.get('turn_start_time', 0) > 300:
                games_to_remove.append(game_id)
                continue

            if game['phase'] == 'playing':
                time_since_turn_start = time.time() - game.get('turn_start_time', 0)
                if time_since_turn_start > TURN_TIMEOUT:
                    current_player_num = game['turn']
                    current_player_name = game['players'][current_player_num]['name']
                    logging.info(f"Game {game_id}: {current_player_name}'s turn timed out.")
                    
                    game['turn'] = 2 if current_player_num == 1 else 1
                    game['turn_start_time'] = time.time()
                    game['status_message'] = f"{current_player_name}'s turn timed out. It's now {game['players'][game['turn']]['name']}'s turn."

            if len(game['players']) < 2:
                continue

            for player_num, player_data in game['players'].items():
                if player_data['connected'] and time.time() - player_data.get('last_activity', 0) > CLIENT_INACTIVITY_TIMEOUT:
                    player_data['connected'] = False
                    logging.info(f"Game {game_id}: Player {player_data['name']} marked as disconnected.")
                    
                    if all(not p.get('connected') for p in game['players'].values()):
                        games_to_remove.append(game_id)

        for game_id in games_to_remove:
            if game_id in GAMES:
                del GAMES[game_id]
                logging.info(f"Removed inactive/finished game {game_id}")

        time.sleep(1)


# --- Threading and Socket Server ---
httpserver = BattleshipHttpServer()

class ProcessTheClient(threading.Thread):
    def __init__(self, connection, address):
        self.connection = connection
        self.address = address
        threading.Thread.__init__(self)

    def run(self):
        request_data = b''
        try:
            self.connection.settimeout(1)
            while True:
                chunk = self.connection.recv(4096)
                if not chunk:
                    break
                request_data += chunk
                if b'\r\n\r\n' in request_data:
                    break
        except socket.timeout:
            pass 
        except Exception as e:
            logging.error(f"Error receiving data: {e}")
        
        if request_data:
            request_str = request_data.decode('utf-8')
            logging.info(f"Request from {self.address}:\n--- START ---\n{request_str[:500]}\n--- END ---")
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
    housekeeping_thread = threading.Thread(target=game_housekeeping, daemon=True)
    housekeeping_thread.start()

    svr = Server()
    svr.start()

if __name__ == "__main__":
    main()