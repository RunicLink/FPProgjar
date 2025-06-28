import socket
import threading
import json
import uuid
import time
from battleship.game_logic import BattleshipGame

class BattleshipServer:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.clients = {}
        self.games = {}
        self.waiting_players = []
        self.lock = threading.Lock()

    def start(self):
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)
        print(f"Battleship server started on {self.host}:{self.port}")

        # --- ADDED: Thread to check for turn timeouts ---
        timeout_thread = threading.Thread(target=self.check_turn_timeouts)
        timeout_thread.daemon = True
        timeout_thread.start()
        
        while True:
            client_socket, address = self.socket.accept()
            print(f"Connection from {address}")
            client_thread = threading.Thread(target=self.handle_client, args=(client_socket, address))
            client_thread.start()

    def check_turn_timeouts(self):
        while True:
            with self.lock:
                # Iterate over a copy of items to avoid runtime errors during modification
                for game_id, game_info in list(self.games.items()):
                    if not game_info.get('game_started') or 'turn_start_time' not in game_info:
                        continue
                    
                    # 60-second turn timer
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

                        self.send_message(timed_out_player_id, {'type': 'turn_timeout', 'message': 'Your turn timed out!', 'your_turn': False, **turn_info})
                        self.send_message(next_player_id, {'type': 'turn_timeout', 'message': "Opponent's turn timed out. Your turn!", 'your_turn': True, **turn_info})

            time.sleep(1) # Check every second

    def handle_client(self, client_socket, address):
        client_id = str(uuid.uuid4())
        self.clients[client_id] = {
            'socket': client_socket,
            'address': address,
            'game_id': None,
            'player_number': None
        }
        
        try:
            while True:
                data = client_socket.recv(1024).decode('utf-8')
                if not data:
                    break
                
                message = json.loads(data)
                self.process_message(client_id, message)
                
        except Exception as e:
            print(f"Error handling client {client_id}: {e}")
        finally:
            self.disconnect_client(client_id)

    def process_message(self, client_id, message):
        msg_type = message.get('type')
        
        if msg_type == 'join_game':
            self.join_game(client_id)
        elif msg_type == 'place_ships':
            self.place_ships(client_id, message['ships'])
        elif msg_type == 'attack':
            self.attack(client_id, message['row'], message['col'])
        elif msg_type == 'get_game_state':
            self.send_game_state(client_id)

    def join_game(self, client_id):
        with self.lock:
            if len(self.waiting_players) == 0:
                self.waiting_players.append(client_id)
                self.send_message(client_id, {'type': 'waiting', 'message': 'Waiting for another player...'})
            else:
                player1_id = self.waiting_players.pop(0)
                player2_id = client_id
                
                game_id = str(uuid.uuid4())
                game = BattleshipGame()
                
                self.games[game_id] = {
                    'game': game,
                    'player1': player1_id,
                    'player2': player2_id,
                    'current_turn': player1_id,
                    'player1_ready': False,
                    'player2_ready': False,
                    'game_started': False
                }
                
                self.clients[player1_id]['game_id'] = game_id
                self.clients[player1_id]['player_number'] = 1
                self.clients[player2_id]['game_id'] = game_id
                self.clients[player2_id]['player_number'] = 2
                
                self.send_message(player1_id, {'type': 'game_found', 'player_number': 1, 'message': 'Game found! Place your ships.'})
                self.send_message(player2_id, {'type': 'game_found', 'player_number': 2, 'message': 'Game found! Place your ships.'})

    def place_ships(self, client_id, ships_data):
        with self.lock:
            game_id = self.clients[client_id]['game_id']
            if not game_id or game_id not in self.games:
                return
            
            game_info = self.games[game_id]
            game = game_info['game']
            player_number = self.clients[client_id]['player_number']
            
            if player_number == 1:
                player_board, player_ships = game.player1_board, game.player1_ships
            else:
                player_board, player_ships = game.player2_board, game.player2_ships
            
            for row in range(game.board_size):
                for col in range(game.board_size):
                    if player_board[row][col] not in ['.', 'X', 'O']:
                        player_board[row][col] = '.'
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
                
                self.send_message(client_id, {'type': 'ships_placed', 'success': True, 'message': 'Ships placed successfully!'})
                
                if game_info['player1_ready'] and game_info['player2_ready']:
                    game_info['game_started'] = True
                    # --- MODIFIED: Set initial turn timer ---
                    game_info['turn_start_time'] = time.time()
                    turn_info = {'turn_start_time': game_info['turn_start_time'], 'turn_duration': 60}
                    
                    self.send_message(game_info['player1'], {'type': 'game_start', 'your_turn': True, 'message': 'Game started! Your turn to attack.', **turn_info})
                    self.send_message(game_info['player2'], {'type': 'game_start', 'your_turn': False, 'message': 'Game started! Wait for your turn.', **turn_info})
            else:
                self.send_message(client_id, {'type': 'ships_placed', 'success': False, 'message': 'Failed to place ships. Try again.'})

    def attack(self, client_id, row, col):
        with self.lock:
            game_id = self.clients[client_id]['game_id']
            if not game_id or game_id not in self.games: return
            
            game_info = self.games[game_id]
            if not game_info['game_started'] or game_info['current_turn'] != client_id:
                self.send_message(client_id, {'type': 'attack_result', 'success': False, 'message': 'Not your turn!'})
                return
            
            game = game_info['game']
            player_number = self.clients[client_id]['player_number']
            
            opponent_board, opponent_ships = (game.player2_board, game.player2_ships) if player_number == 1 else (game.player1_board, game.player1_ships)
            
            result = game.attack(opponent_board, opponent_ships, row, col)
            
            # --- MODIFIED: Added logic for sunk ships and unconditional turn switching ---
            sunk_ship_info = None
            if "sunk" in result:
                sunk_ship_name = result.split("sunk ")[1].replace("!", "")
                sunk_ship_info = {'player': 2 if player_number == 1 else 1, 'ship_name': sunk_ship_name}

            if result in ["Hit", "Miss"] or "sunk" in result:
                # Always switch turns after a valid attack
                if game_info['current_turn'] == game_info['player1']:
                    game_info['current_turn'] = game_info['player2']
                else:
                    game_info['current_turn'] = game_info['player1']
                
                game_info['turn_start_time'] = time.time()
                game_over = self.check_game_over(game_info)
                turn_info = {'turn_start_time': game_info['turn_start_time'], 'turn_duration': 60}

                # --- MODIFIED: Added row and col to messages ---
                # Notify attacker
                self.send_message(client_id, {'type': 'attack_result', 'success': True, 'result': result, 'your_turn': False, 'game_over': game_over, 'sunk_ship_info': sunk_ship_info, 'row': row, 'col': col, **turn_info})
                
                # Notify opponent
                opponent_id = game_info['player2'] if player_number == 1 else game_info['player1']
                self.send_message(opponent_id, {'type': 'opponent_attack', 'result': result, 'your_turn': not game_over, 'game_over': game_over, 'sunk_ship_info': sunk_ship_info, 'row': row, 'col': col, **turn_info})
                
                if game_over:
                    winner = f"Player {player_number}"
                    self.send_message(game_info['player1'], {'type': 'game_over', 'winner': winner})
                    self.send_message(game_info['player2'], {'type': 'game_over', 'winner': winner})
            else:
                self.send_message(client_id, {'type': 'attack_result', 'success': False, 'message': result})

    def check_game_over(self, game_info):
        game = game_info['game']
        p1_wins = game.check_game_over(game.player2_board, game.player2_ships)
        if p1_wins:
            return True
        
        p2_wins = game.check_game_over(game.player1_board, game.player1_ships)
        if p2_wins:
            return True
            
        return False

    def send_game_state(self, client_id):
        with self.lock:
            game_id = self.clients[client_id]['game_id']
            if not game_id or game_id not in self.games:
                return
            
            game_info = self.games[game_id]
            game = game_info['game']
            player_number = self.clients[client_id]['player_number']
            
            if player_number == 1:
                own_board = game.player1_board
                opponent_board = game.player2_board
            else:
                own_board = game.player2_board
                opponent_board = game.player1_board
            
            # Create a safe version of opponent board (hide ships)
            safe_opponent_board = []
            for row in opponent_board:
                safe_row = []
                for cell in row:
                    if cell in ['X', 'O']:
                        safe_row.append(cell)
                    else:
                        safe_row.append('.')
                safe_opponent_board.append(safe_row)
            
            self.send_message(client_id, {
                'type': 'game_state',
                'own_board': own_board,
                'opponent_board': safe_opponent_board,
                'your_turn': game_info['current_turn'] == client_id,
                'game_started': game_info['game_started']
            })
            pass

    def send_message(self, client_id, message):
        if client_id in self.clients:
            try:
                self.clients[client_id]['socket'].send(json.dumps(message).encode('utf-8'))
            except:
                pass

    def disconnect_client(self, client_id):
        with self.lock:
            if client_id in self.clients:
                client_socket = self.clients[client_id]['socket']
                client_socket.close()
                
                if client_id in self.waiting_players:
                    self.waiting_players.remove(client_id)
                
                game_id = self.clients[client_id].get('game_id')
                if game_id and game_id in self.games:
                    game_info = self.games[game_id]
                    opponent_id = game_info['player2'] if game_info['player1'] == client_id else game_info['player1']
                    
                    if opponent_id in self.clients:
                        self.send_message(opponent_id, {'type': 'opponent_disconnected', 'message': 'Your opponent has disconnected. Game over.'})
                    
                    del self.games[game_id]
                
                del self.clients[client_id]
                print(f"Client {client_id} disconnected")

if __name__ == '__main__':
    server = BattleshipServer('0.0.0.0', 8888)
    server.start()