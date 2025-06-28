# server.py
import socket
import threading
import json
import uuid
import time
import random # For room code generation
from battleship.game_logic import BattleshipGame

class GameManager:
    def __init__(self):
        self.games = {}  # game_id -> game_info
        self.clients = {} # client_id -> client_info
        self.waiting_private_hosts = {} # room_code -> client_id (host)
        self.waiting_quick_play = [] # list of client_ids
        self.lock = threading.Lock()

    def generate_room_code(self):
        while True:
            code = ''.join(random.choices('0123456789', k=6))
            if code not in self.waiting_private_hosts and code not in self.games:
                return code

    def host_game(self, client_id, player_name):
        with self.lock:
            room_code = self.generate_room_code()
            self.waiting_private_hosts[room_code] = client_id
            self.clients[client_id]['player_name'] = player_name
            self.clients[client_id]['room_code'] = room_code
            self.clients[client_id]['game_type'] = 'private'
            return room_code

    def join_private_game(self, client_id, player_name, room_code):
        with self.lock:
            if room_code in self.waiting_private_hosts:
                player1_id = self.waiting_private_hosts.pop(room_code)
                
                game_id = str(uuid.uuid4())
                game = BattleshipGame()
                
                self.games[game_id] = {
                    'game': game,
                    'player1': player1_id,
                    'player2': client_id,
                    'player1_name': self.clients[player1_id].get('player_name', 'Player 1'),
                    'player2_name': player_name,
                    'current_turn': player1_id,
                    'player1_ready': False,
                    'player2_ready': False,
                    'game_started': False,
                    'game_type': 'private',
                    'spectators': []
                }
                
                self.clients[player1_id]['game_id'] = game_id
                self.clients[player1_id]['player_number'] = 1
                self.clients[client_id]['game_id'] = game_id
                self.clients[client_id]['player_number'] = 2
                self.clients[client_id]['player_name'] = player_name
                self.clients[client_id]['room_code'] = room_code
                self.clients[client_id]['game_type'] = 'private'
                
                # Notify both players that game is found
                self.send_message(player1_id, {'type': 'game_found', 'player_number': 1, 'room_code': room_code, 'player_name': self.games[game_id]['player1_name'], 'opponent_name': player_name, 'message': 'Game found! Place your ships.'})
                self.send_message(client_id, {'type': 'game_found', 'player_number': 2, 'room_code': room_code, 'player_name': player_name, 'opponent_name': self.games[game_id]['player1_name'], 'message': 'Game found! Place your ships.'})
                return True, "Game joined successfully!"
            else:
                return False, "Invalid room code or room is full."

    def quick_play(self, client_id):
        with self.lock:
            if len(self.waiting_quick_play) == 0:
                self.waiting_quick_play.append(client_id)
                self.clients[client_id]['game_type'] = 'quick_play'
                return True, "Waiting for another player..."
            else:
                player1_id = self.waiting_quick_play.pop(0)
                player2_id = client_id
                
                game_id = str(uuid.uuid4())
                game = BattleshipGame()
                
                self.games[game_id] = {
                    'game': game,
                    'player1': player1_id,
                    'player2': player2_id,
                    'player1_name': 'Player 1',
                    'player2_name': 'Player 2',
                    'current_turn': player1_id,
                    'player1_ready': False,
                    'player2_ready': False,
                    'game_started': False,
                    'game_type': 'quick_play',
                    'spectators': []
                }
                
                self.clients[player1_id]['game_id'] = game_id
                self.clients[player1_id]['player_number'] = 1
                self.clients[client_id]['game_id'] = game_id
                self.clients[client_id]['player_number'] = 2
                self.clients[client_id]['game_type'] = 'quick_play'
                
                self.send_message(player1_id, {'type': 'game_found', 'player_number': 1, 'player_name': 'Player 1', 'opponent_name': 'Player 2', 'message': 'Game found! Place your ships.'})
                self.send_message(client_id, {'type': 'game_found', 'player_number': 2, 'player_name': 'Player 2', 'opponent_name': 'Player 1', 'message': 'Game found! Place your ships.'})
                return True, "Game found!"

    def get_public_games_list(self):
        with self.lock:
            game_list = []
            for game_id, game_info in self.games.items():
                if game_info['game_type'] == 'quick_play' and game_info['game_started']:
                    game_list.append({
                        'game_id': game_id,
                        'player1_name': game_info['player1_name'],
                        'player2_name': game_info['player2_name']
                    })
            return game_list

    def spectate_game(self, client_id, game_id):
        with self.lock:
            if game_id in self.games and self.games[game_id]['game_type'] == 'quick_play':
                self.games[game_id]['spectators'].append(client_id)
                self.clients[client_id]['game_id'] = game_id
                self.clients[client_id]['is_spectator'] = True
                game_info = self.games[game_id]
                self.send_message(client_id, {
                    'type': 'spectate_start',
                    'game_id': game_id,
                    'player1_name': game_info['player1_name'],
                    'player2_name': game_info['player2_name'],
                    'current_turn_player_name': game_info['player1_name'] if game_info['current_turn'] == game_info['player1'] else game_info['player2_name'],
                    'game_started': game_info['game_started']
                })
                self.send_spectator_game_state(game_id)
                return True, "Spectating game."
            return False, "Invalid game ID or private game."

    def send_message(self, client_id, message):
        if client_id in self.clients and self.clients[client_id]['socket']:
            try:
                self.clients[client_id]['socket'].send(json.dumps(message).encode('utf-8'))
            except Exception as e:
                print(f"Error sending to {client_id}: {e}")
                self.disconnect_client(client_id) # Consider disconnecting if send fails

    def send_game_state_to_players(self, game_id):
        game_info = self.games[game_id]
        game = game_info['game']

        # Player 1's state
        self._send_single_player_game_state(game_info['player1'], game_info['player1'], game_info['player2'], game)
        # Player 2's state
        self._send_single_player_game_state(game_info['player2'], game_info['player2'], game_info['player1'], game)
        
        self.send_spectator_game_state(game_id)

    def _send_single_player_game_state(self, client_id, own_id, opponent_id, game):
        player_number = self.clients[client_id]['player_number']
        
        if player_number == 1:
            own_board = game.player1_board
            opponent_board = game.player2_board
            player_name = self.games[self.clients[client_id]['game_id']]['player1_name']
            opponent_name = self.games[self.clients[client_id]['game_id']]['player2_name']
        else:
            own_board = game.player2_board
            opponent_board = game.player1_board
            player_name = self.games[self.clients[client_id]['game_id']]['player2_name']
            opponent_name = self.games[self.clients[client_id]['game_id']]['player1_name']
        
        safe_opponent_board = []
        for row in opponent_board:
            safe_row = []
            for cell in row:
                if cell in ['X', 'O']:
                    safe_row.append(cell)
                else:
                    safe_row.append('.')
            safe_opponent_board.append(safe_row)

        game_info = self.games[self.clients[client_id]['game_id']]
        current_turn_player_name = game_info['player1_name'] if game_info['current_turn'] == game_info['player1'] else game_info['player2_name']

        self.send_message(client_id, {
            'type': 'game_state',
            'own_board': own_board,
            'opponent_board': safe_opponent_board,
            'your_turn': game_info['current_turn'] == client_id,
            'game_started': game_info['game_started'],
            'player_name': player_name,
            'opponent_name': opponent_name,
            'current_turn_player_name': current_turn_player_name
        })

    def send_spectator_game_state(self, game_id):
        game_info = self.games[game_id]
        game = game_info['game']

        player1_board_safe = []
        for row in game.player1_board:
            safe_row = []
            for cell in row:
                safe_row.append(cell if cell in ['X', 'O'] else '.') # Spectators only see hits/misses on the actual board
            player1_board_safe.append(safe_row)

        player2_board_safe = []
        for row in game.player2_board:
            safe_row = []
            for cell in row:
                safe_row.append(cell if cell in ['X', 'O'] else '.') # Spectators only see hits/misses on the actual board
            player2_board_safe.append(safe_row)
        
        current_turn_player_name = game_info['player1_name'] if game_info['current_turn'] == game_info['player1'] else game_info['player2_name']

        for spec_id in game_info['spectators']:
            self.send_message(spec_id, {
                'type': 'game_state',
                'player1_board': player1_board_safe,
                'player2_board': player2_board_safe,
                'game_started': game_info['game_started'],
                'player1_name': game_info['player1_name'],
                'player2_name': game_info['player2_name'],
                'current_turn_player_name': current_turn_player_name
            })

    def disconnect_client(self, client_id):
        with self.lock:
            if client_id in self.clients:
                # Remove from waiting lists
                if client_id in self.waiting_quick_play:
                    self.waiting_quick_play.remove(client_id)
                for code, host_id in list(self.waiting_private_hosts.items()):
                    if host_id == client_id:
                        del self.waiting_private_hosts[code]
                        break

                game_id = self.clients[client_id].get('game_id')
                if game_id and game_id in self.games:
                    game_info = self.games[game_id]
                    
                    # Remove from spectators if applicable
                    if client_id in game_info['spectators']:
                        game_info['spectators'].remove(client_id)
                    
                    # Handle player disconnection
                    elif client_id == game_info['player1'] or client_id == game_info['player2']:
                        opponent_id = None
                        if client_id == game_info['player1']:
                            opponent_id = game_info['player2']
                        elif client_id == game_info['player2']:
                            opponent_id = game_info['player1']

                        if opponent_id and opponent_id in self.clients:
                            self.send_message(opponent_id, {'type': 'opponent_disconnected', 'message': 'Your opponent has disconnected. Game over.'})
                        
                        # Notify spectators
                        for spec_id in game_info['spectators']:
                            self.send_message(spec_id, {'type': 'game_over', 'winner': 'N/A', 'message': 'Game ended due to player disconnection.'})

                        del self.games[game_id]
                
                client_socket = self.clients[client_id]['socket']
                client_socket.close()
                del self.clients[client_id]
                print(f"Client {client_id} disconnected")


class BattleshipServer:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.game_manager = GameManager() # Use GameManager for all game logic

    def start(self):
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)
        print(f"Battleship server started on {self.host}:{self.port}")

        timeout_thread = threading.Thread(target=self.check_turn_timeouts)
        timeout_thread.daemon = True
        timeout_thread.start()
        
        while True:
            client_socket, address = self.socket.accept()
            print(f"Connection from {address}")
            client_id = str(uuid.uuid4())
            self.game_manager.clients[client_id] = {
                'socket': client_socket,
                'address': address,
                'game_id': None,
                'player_number': None,
                'player_name': 'Unknown',
                'is_spectator': False
            }
            client_thread = threading.Thread(target=self.handle_client, args=(client_id, client_socket))
            client_thread.start()

    def check_turn_timeouts(self):
        while True:
            with self.game_manager.lock:
                for game_id, game_info in list(self.game_manager.games.items()):
                    if not game_info.get('game_started') or 'turn_start_time' not in game_info:
                        continue
                    
                    if time.time() - game_info['turn_start_time'] > 60:
                        print(f"Game {game_id}: Turn timed out.")
                        
                        current_player_id = game_info['current_turn']
                        if current_player_id == game_info['player1']:
                            timed_out_player_id = game_info['player1']
                            next_player_id = game_info['player2']
                            game_info['current_turn'] = next_player_id
                        else:
                            timed_out_player_id = game_info['player2']
                            next_player_id = game_info['player1']
                            game_info['current_turn'] = next_player_id
                        
                        game_info['turn_start_time'] = time.time()
                        turn_info = {'turn_start_time': game_info['turn_start_time'], 'turn_duration': 60}

                        self.game_manager.send_message(timed_out_player_id, {'type': 'turn_timeout', 'message': 'Your turn timed out!', 'your_turn': False, **turn_info})
                        self.game_manager.send_message(next_player_id, {'type': 'turn_timeout', 'message': "Opponent's turn timed out. Your turn!", 'your_turn': True, **turn_info})
                        
                        # Update spectators on turn change
                        self.game_manager.send_spectator_game_state(game_id)
            time.sleep(1)

    def handle_client(self, client_id, client_socket):
        try:
            while True:
                data = client_socket.recv(4096).decode('utf-8')
                if not data:
                    break
                
                # Handle multiple JSON objects in one go
                for message_str in data.split('}{'):
                    if not message_str.startswith('{'):
                        message_str = '{' + message_str
                    if not message_str.endswith('}'):
                        message_str = message_str + '}'
                    
                    try:
                        message = json.loads(message_str)
                        self.process_message(client_id, message)
                    except json.JSONDecodeError:
                        print(f"Skipping malformed JSON from {client_id}: {message_str}")
                
        except Exception as e:
            print(f"Error handling client {client_id}: {e}")
        finally:
            self.game_manager.disconnect_client(client_id)

    def process_message(self, client_id, message):
        msg_type = message.get('type')
        
        if msg_type == 'host_game':
            player_name = message.get('player_name', 'Host')
            room_code = self.game_manager.host_game(client_id, player_name)
            self.game_manager.send_message(client_id, {'type': 'waiting', 'message': 'Waiting for another player...', 'room_code': room_code})
            self.game_manager.send_message(client_id, {'type': 'room_code', 'code': room_code}) # Send room code explicitly
        elif msg_type == 'join_private_game':
            player_name = message.get('player_name', 'Player')
            room_code = message.get('room_code')
            success, msg = self.game_manager.join_private_game(client_id, player_name, room_code)
            self.game_manager.send_message(client_id, {'type': 'room_join_status', 'success': success, 'message': msg})
        elif msg_type == 'quick_play':
            success, msg = self.game_manager.quick_play(client_id)
            # FIX: Only send 'waiting' message if the player is actually waiting.
            # The game_manager.quick_play method sends 'game_found' itself when a match is made.
            if "Waiting" in msg:
                self.game_manager.send_message(client_id, {'type': 'waiting', 'message': msg})
        elif msg_type == 'place_ships':
            self.place_ships(client_id, message['ships'])
        elif msg_type == 'attack':
            self.attack(client_id, message['row'], message['col'])
        elif msg_type == 'get_game_state':
            self.game_manager.send_game_state_to_players(self.game_manager.clients[client_id]['game_id'])
        elif msg_type == 'get_game_list':
            game_list = self.game_manager.get_public_games_list()
            self.game_manager.send_message(client_id, {'type': 'game_list', 'games': game_list})
        elif msg_type == 'spectate_game':
            game_id = message.get('game_id')
            success, msg = self.game_manager.spectate_game(client_id, game_id)
            if not success:
                self.game_manager.send_message(client_id, {'type': 'spectate_status', 'success': False, 'message': msg})


    def place_ships(self, client_id, ships_data):
        with self.game_manager.lock:
            game_id = self.game_manager.clients[client_id]['game_id']
            if not game_id or game_id not in self.game_manager.games:
                return
            
            game_info = self.game_manager.games[game_id]
            game = game_info['game']
            player_number = self.game_manager.clients[client_id]['player_number']
            
            if player_number == 1:
                player_board, player_ships = game.player1_board, game.player1_ships
            else:
                player_board, player_ships = game.player2_board, game.player2_ships
            
            # Clear existing ships on the board before placing new ones
            for r in range(game.board_size):
                for c in range(game.board_size):
                    if player_board[r][c] not in ['.', 'X', 'O']: # Only clear ship markers, not hits/misses
                        player_board[r][c] = '.'
            player_ships.clear()
            
            all_placed = True
            for ship_data in ships_data:
                if not game.place_ship(player_board, player_ships, ship_data['name'], game.ships[ship_data['name']], ship_data['start_row'], ship_data['start_col'], ship_data['orientation']):
                    all_placed = False
                    break
            
            if all_placed:
                if player_number == 1:
                    game_info['player1_ready'] = True
                else:
                    game_info['player2_ready'] = True
                
                self.game_manager.send_message(client_id, {'type': 'ships_placed', 'success': True, 'message': 'Ships placed successfully!'})
                self.game_manager.send_game_state_to_players(game_id) # Update boards after placing ships
                
                if game_info['player1_ready'] and game_info['player2_ready']:
                    game_info['game_started'] = True
                    game_info['turn_start_time'] = time.time()
                    turn_info = {'turn_start_time': game_info['turn_start_time'], 'turn_duration': 60}
                    
                    p1_name = game_info['player1_name']
                    p2_name = game_info['player2_name']

                    self.game_manager.send_message(game_info['player1'], {'type': 'game_start', 'your_turn': True, 'player_name': p1_name, 'opponent_name': p2_name, 'current_turn_player_name': p1_name, 'message': 'Game started! Your turn to attack.', **turn_info})
                    self.game_manager.send_message(game_info['player2'], {'type': 'game_start', 'your_turn': False, 'player_name': p2_name, 'opponent_name': p1_name, 'current_turn_player_name': p1_name, 'message': 'Game started! Wait for your turn.', **turn_info})
                    
                    self.game_manager.send_spectator_game_state(game_id) # Notify spectators that game has started
            else:
                self.game_manager.send_message(client_id, {'type': 'ships_placed', 'success': False, 'message': 'Failed to place ships. Try again.'})

    def attack(self, client_id, row, col):
        with self.game_manager.lock:
            game_id = self.game_manager.clients[client_id]['game_id']
            if not game_id or game_id not in self.game_manager.games: return
            
            game_info = self.game_manager.games[game_id]
            if not game_info['game_started'] or game_info['current_turn'] != client_id:
                self.game_manager.send_message(client_id, {'type': 'attack_result', 'success': False, 'message': 'Not your turn!'})
                return
            
            game = game_info['game']
            player_number = self.game_manager.clients[client_id]['player_number']
            
            opponent_board, opponent_ships = (game.player2_board, game.player2_ships) if player_number == 1 else (game.player1_board, game.player1_ships)
            
            result = game.attack(opponent_board, opponent_ships, row, col)
            
            sunk_ship_info = None
            if "sunk" in result:
                sunk_ship_name = result.split("sunk ")[1].replace("!", "")
                # Determine which player's ship was sunk for client display
                sunk_player_number = 2 if player_number == 1 else 1 
                sunk_ship_info = {'player': sunk_player_number, 'ship_name': sunk_ship_name}

            if result in ["Hit", "Miss"] or "sunk" in result:
                # Always switch turns after a valid attack
                if game_info['current_turn'] == game_info['player1']:
                    game_info['current_turn'] = game_info['player2']
                else:
                    game_info['current_turn'] = game_info['player1']
                
                game_info['turn_start_time'] = time.time()
                game_over = self.check_game_over(game_info)
                turn_info = {'turn_start_time': game_info['turn_start_time'], 'turn_duration': 60}

                current_turn_player_name = game_info['player1_name'] if game_info['current_turn'] == game_info['player1'] else game_info['player2_name']

                # Notify attacker
                self.game_manager.send_message(client_id, {'type': 'attack_result', 'success': True, 'result': result, 'your_turn': False, 'game_over': game_over, 'sunk_ship_info': sunk_ship_info, 'row': row, 'col': col, 'current_turn_player_name': current_turn_player_name, **turn_info})
                
                # Notify opponent
                opponent_id = game_info['player2'] if player_number == 1 else game_info['player1']
                self.game_manager.send_message(opponent_id, {'type': 'opponent_attack', 'result': result, 'your_turn': not game_over, 'game_over': game_over, 'sunk_ship_info': sunk_ship_info, 'row': row, 'col': col, 'current_turn_player_name': current_turn_player_name, **turn_info})
                
                # Send updated game state to both players and spectators
                self.game_manager.send_game_state_to_players(game_id)
                self.game_manager.send_spectator_game_state(game_id)


                if game_over:
                    winner_id = client_id # The player who made the last successful attack
                    winner_name = game_info['player1_name'] if winner_id == game_info['player1'] else game_info['player2_name']
                    self.game_manager.send_message(game_info['player1'], {'type': 'game_over', 'winner': winner_name})
                    self.game_manager.send_message(game_info['player2'], {'type': 'game_over', 'winner': winner_name})
                    for spec_id in game_info['spectators']:
                         self.game_manager.send_message(spec_id, {'type': 'game_over', 'winner': winner_name})
            else:
                self.game_manager.send_message(client_id, {'type': 'attack_result', 'success': False, 'message': result})

    def check_game_over(self, game_info):
        game = game_info['game']
        # Game is over if all of Player 2's ships are sunk (Player 1 wins)
        # OR all of Player 1's ships are sunk (Player 2 wins)
        
        p1_won = game.check_game_over(game.player2_board, game.player2_ships) # Check if player 2's board (opponent of P1) is all hit
        if p1_won:
            return True
        
        p2_won = game.check_game_over(game.player1_board, game.player1_ships) # Check if player 1's board (opponent of P2) is all hit
        if p2_won:
            return True
            
        return False

if __name__ == '__main__':
    server = BattleshipServer('0.0.0.0', 8888)
    server.start()