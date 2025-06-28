# battleship_server_http.py
import socket
import threading
import json
import uuid
import time
import logging
from battleship.game_logic import BattleshipGame

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

GAMES = {}
GAME_LOGIC = BattleshipGame()
TURN_TIMEOUT = 60 
CLIENT_INACTIVITY_TIMEOUT = 5  # 10 seconds of inactivity before marking as disconnected
RECONNECT_WINDOW_SECONDS = 60  # NEW: Duration of the pause for reconnection

# Quick Match Queue - stores players waiting for quick match
QUICK_MATCH_QUEUE = []
QUICK_MATCH_TIMEOUT = 120  # 2 minutes timeout for quick match queue
QUICK_MATCH_LOCK = threading.Lock()  # Thread lock for queue operations

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
            "Connection": "keep-alive",
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
            
            current_status_message = game['status_message'] # Start with the default message.

            if game['phase'] == 'paused':
                pause_start = game.get('pause_start_time', 0)
                elapsed = time.time() - pause_start
                time_remaining = max(0, RECONNECT_WINDOW_SECONDS - elapsed)

                # Overwrite the status message with our dynamic countdown.
                current_status_message = f"Game Paused. Waiting {int(time_remaining)} seconds for the other player to reconnect."

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
                'status_message': current_status_message,
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

        # Quick Match endpoints
        if path == '/api/quick_match':
            return self.handle_quick_match(payload)
            
        if path == '/api/cancel_quick_match':
            return self.handle_cancel_quick_match(payload)
            
        if path == '/api/check_quick_match':
            return self.handle_check_quick_match(payload)

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
        
        reconnecting_player_number = None
        for p_num, p_data in game['players'].items():
            if p_data['name'] == player_name:
                reconnecting_player_number = p_num
                break

        if reconnecting_player_number:
            # --- NEW LOGIC FOR RESUMING A PAUSED GAME ---
            if game['phase'] == 'paused' and game.get('disconnected_player_num') == reconnecting_player_number:
                logging.info(f"Player {player_name} reconnected to game {game_id}. Resuming.")
                game['players'][reconnecting_player_number]['connected'] = True
                game['players'][reconnecting_player_number]['last_activity'] = time.time()
                
                # Un-pause the game
                game['phase'] = 'playing'
                # Reset the turn timer to give the current player a full turn
                game['turn_start_time'] = time.time()
                game['status_message'] = f"{player_name} has reconnected. Resuming game."
                
                # Clean up pause-related fields
                if 'pause_start_time' in game: del game['pause_start_time']
                if 'disconnected_player_num' in game: del game['disconnected_player_num']
                
                return self.response(200, 'OK', {'game_id': game_id, 'player_number': reconnecting_player_number, 'reconnected': True})
            
            # Original reconnect logic for a player that may have been marked disconnected but game not paused
            elif not game['players'][reconnecting_player_number]['connected']:
                game['players'][reconnecting_player_number]['connected'] = True
                game['players'][reconnecting_player_number]['last_activity'] = time.time()
                logging.info(f"Player {player_name} reconnected to game {game_id} as player {reconnecting_player_number}")
                return self.response(200, 'OK', {'game_id': game_id, 'player_number': reconnecting_player_number, 'reconnected': True})
            
            else: # Player is already connected and game is not paused
                 return self.response(403, 'Forbidden', {'error': 'Player is already connected to this game.'})
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

    def handle_quick_match(self, payload):
        """Handle quick match request - join queue and try to match with other players"""
        player_name = payload.get('player_name')
        if not player_name:
            return self.response(400, 'Bad Request', {'error': 'Player name is required'})
        
        with QUICK_MATCH_LOCK:
            # Remove player from any finished games to avoid conflicts
            games_to_clean = []
            for game_id, game in GAMES.items():
                if game['phase'] == 'game_over':
                    for player_num, player_data in game['players'].items():
                        if player_data['name'] == player_name:
                            games_to_clean.append(game_id)
                            break
            
            for game_id in games_to_clean:
                if game_id in GAMES:
                    del GAMES[game_id]
                    logging.info(f"Cleaned up finished game {game_id} for player {player_name}")
            
            # Check if player is already in queue
            for queued_player in QUICK_MATCH_QUEUE:
                if queued_player['name'] == player_name:
                    return self.response(400, 'Bad Request', {'error': 'Already in quick match queue'})
            
            # Try to match with another player first
            if len(QUICK_MATCH_QUEUE) >= 1:
                # Get the first player from queue
                player1 = QUICK_MATCH_QUEUE.pop(0)
                player2 = {'name': player_name, 'timestamp': time.time()}
                
                # Create game
                game_id = str(uuid.uuid4())[:8]
                GAMES[game_id] = {
                    'game_id': game_id,
                    'players': {
                        1: {'name': player1['name'], 'ships_placed': False, 'connected': True, 'last_activity': time.time(), 'placed_ships_data': []},
                        2: {'name': player2['name'], 'ships_placed': False, 'connected': True, 'last_activity': time.time(), 'placed_ships_data': []}
                    },
                    'player_boards': {1: [['.' for _ in range(10)] for _ in range(10)], 2: [['.' for _ in range(10)] for _ in range(10)]},
                    'player_ships': {1: {}, 2: {}},
                    'sunk_ships': {1: [], 2: []},
                    'turn': 1,
                    'phase': 'placing_ships',
                    'status_message': 'Quick match found! Place your ships.',
                    'turn_start_time': 0,
                    'is_quick_match': True
                }
                
                logging.info(f"Quick match created: {game_id} with {player1['name']} vs {player2['name']}")
                
                # Return game info for the requesting player (player2 in this case)
                return self.response(200, 'OK', {
                    'game_id': game_id, 
                    'player_number': 2,
                    'matched': True,
                    'opponent_name': player1['name']
                })
            else:
                # Add player to queue
                queue_entry = {
                    'name': player_name,
                    'timestamp': time.time()
                }
                QUICK_MATCH_QUEUE.append(queue_entry)
                logging.info(f"Player {player_name} joined quick match queue")
                
                # Still waiting for opponent
                return self.response(200, 'OK', {'matched': False, 'waiting': True})

    def handle_cancel_quick_match(self, payload):
        """Handle cancel quick match request"""
        player_name = payload.get('player_name')
        if not player_name:
            return self.response(400, 'Bad Request', {'error': 'Player name is required'})
        
        with QUICK_MATCH_LOCK:
            # Remove player from queue
            for i, queued_player in enumerate(QUICK_MATCH_QUEUE):
                if queued_player['name'] == player_name:
                    QUICK_MATCH_QUEUE.pop(i)
                    logging.info(f"Player {player_name} cancelled quick match")
                    return self.response(200, 'OK', {'cancelled': True})
        
        return self.response(404, 'Not Found', {'error': 'Not in quick match queue'})

    def handle_check_quick_match(self, payload):
        """Check if a quick match has been found for the player"""
        player_name = payload.get('player_name')
        if not player_name:
            return self.response(400, 'Bad Request', {'error': 'Player name is required'})
        
        with QUICK_MATCH_LOCK:
            # Check if player is still in queue
            for queued_player in QUICK_MATCH_QUEUE:
                if queued_player['name'] == player_name:
                    return self.response(200, 'OK', {'matched': False, 'waiting': True})
        
        # Check if player is in a quick match game (but only active games)
        for game_id, game in GAMES.items():
            if game.get('is_quick_match', False) and game['phase'] != 'game_over':
                for player_num, player_data in game['players'].items():
                    if player_data['name'] == player_name:
                        opponent_num = 2 if player_num == 1 else 1
                        return self.response(200, 'OK', {
                            'matched': True,
                            'game_id': game_id,
                            'player_number': player_num,
                            'opponent_name': game['players'][opponent_num]['name']
                        })
        
        return self.response(404, 'Not Found', {'error': 'Not in quick match queue or game'})


def game_housekeeping():
    """
    A background thread to manage game state, like turn timeouts and disconnections.
    """
    while True:
        games_to_remove = []
        for game_id, game in list(GAMES.items()):
            if game['phase'] == 'playing':
                # (This part of the function is unchanged)
                time_since_turn_start = time.time() - game.get('turn_start_time', 0)
                if time_since_turn_start > TURN_TIMEOUT:
                    # ... turn timeout logic ...
                    current_player_num = game['turn']
                    current_player_name = game['players'][current_player_num]['name']
                    logging.info(f"Game {game_id}: {current_player_name}'s turn timed out.")
                    
                    game['turn'] = 2 if current_player_num == 1 else 1
                    game['turn_start_time'] = time.time()
                    game['status_message'] = f"{current_player_name}'s turn timed out. It's now {game['players'][game['turn']]['name']}'s turn."

                for player_num, player_data in game['players'].items():
                    if player_data['connected'] and time.time() - player_data.get('last_activity', 0) > CLIENT_INACTIVITY_TIMEOUT:
                        player_data['connected'] = False
                        logging.info(f"Game {game_id}: Player {player_data['name']} inactive. Pausing game.")
                        
                        game['phase'] = 'paused'
                        game['pause_start_time'] = time.time()
                        game['disconnected_player_num'] = player_num
                        game['status_message'] = f"{player_data['name']} has disconnected. Reconnection window open."
                        
                        break
            
            elif game['phase'] == 'paused':
                # CHANGED: The check now uses the dynamic constant.
                if time.time() - game.get('pause_start_time', 0) > RECONNECT_WINDOW_SECONDS:
                    logging.info(f"Game {game_id}: Reconnect window closed.")
                    game['phase'] = 'game_over'
                    
                    disconnected_player_num = game.get('disconnected_player_num')
                    winner_num = 2 if disconnected_player_num == 1 else 1
                    
                    if winner_num in game['players']:
                        winner_name = game['players'][winner_num]['name']
                        game['winner_name'] = winner_name
                        game['status_message'] = f"Game Over! {winner_name} wins by opponent disconnect!"
                    else:
                        game['status_message'] = "Game Over! Player disconnected."


            # --- EXISTING LOGIC FOR GAME CLEANUP ---
            if game['phase'] == 'game_over':
                # Give a small grace period before removing the game so clients can get the final state
                # The 'turn_start_time' can be repurposed as 'game_end_time' here.
                if 'game_end_time' not in game:
                    game['game_end_time'] = time.time()
                
                if time.time() - game.get('game_end_time', 0) > 10: # 10 seconds grace period
                    games_to_remove.append(game_id)
                    continue

        for game_id in games_to_remove:
            if game_id in GAMES:
                del GAMES[game_id]
                logging.info(f"Removed inactive/finished game {game_id}")

        # Clean up quick match queue - remove players who have been waiting too long
        with QUICK_MATCH_LOCK:
            current_time = time.time()
            players_to_remove = []
            for i, queued_player in enumerate(QUICK_MATCH_QUEUE):
                if current_time - queued_player['timestamp'] > QUICK_MATCH_TIMEOUT:
                    players_to_remove.append(i)
            
            for i in reversed(players_to_remove):  # Remove from end to avoid index shifting
                removed_player = QUICK_MATCH_QUEUE.pop(i)
                logging.info(f"Removed {removed_player['name']} from quick match queue (timeout)")

        time.sleep(1)


# --- Threading and Socket Server ---
httpserver = BattleshipHttpServer()

class ProcessTheClient(threading.Thread):
    def __init__(self, connection, address):
        self.connection = connection
        self.address = address
        threading.Thread.__init__(self)

    def run(self):
        self.connection.settimeout(10.0)  # 10-second timeout for idle connections
        
        while True:
            try:
                # Read the request headers
                request_data = b''
                while b'\r\n\r\n' not in request_data:
                    chunk = self.connection.recv(4096)
                    if not chunk:
                        # Client closed connection
                        break
                    request_data += chunk
                
                if not request_data:
                    break # Break loop if client disconnected

                # Extract headers and body
                header_part, body_part = request_data.split(b'\r\n\r\n', 1)
                headers = {}
                header_lines = header_part.split(b'\r\n')
                for line in header_lines[1:]:
                    if b': ' in line:
                        key, value = line.split(b': ', 1)
                        headers[key.lower().decode('utf-8')] = value.decode('utf-8')

                # Read the body based on Content-Length
                content_length = int(headers.get('content-length', 0))
                
                while len(body_part) < content_length:
                    body_part += self.connection.recv(4096)

                request_str = request_data.decode('utf-8', errors='ignore')
                logging.info(f"Request from {self.address}:\n--- START ---\n{request_str[:500]}\n--- END ---")

                # Process the request
                response_bytes = httpserver.process(request_str)
                self.connection.sendall(response_bytes)

                # Check if the client requested to close the connection
                if headers.get('connection', 'keep-alive').lower() == 'close':
                    break

            except socket.timeout:
                logging.info(f"Connection from {self.address} timed out. Closing.")
                break
            except (ConnectionResetError, BrokenPipeError):
                logging.info(f"Client {self.address} forcefully closed the connection.")
                break
            except Exception as e:
                logging.error(f"Error processing client {self.address}: {e}")
                break
        
        self.connection.close()
        logging.info(f"Connection closed for {self.address}")


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