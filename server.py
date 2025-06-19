import socket
import threading
import json
import uuid
from game_logic import BattleshipGame

class BattleshipServer:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.clients = {}
        self.games = {}
        self.waiting_players = []

    def start(self):
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)
        print(f"Battleship server started on {self.host}:{self.port}")
        
        while True:
            client_socket, address = self.socket.accept()
            print(f"Connection from {address}")
            client_thread = threading.Thread(target=self.handle_client, args=(client_socket, address))
            client_thread.start()

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
        if len(self.waiting_players) == 0:
            # First player waiting
            self.waiting_players.append(client_id)
            self.send_message(client_id, {
                'type': 'waiting',
                'message': 'Waiting for another player...'
            })
        else:
            # Second player joins, start game
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
            
            self.send_message(player1_id, {
                'type': 'game_found',
                'player_number': 1,
                'message': 'Game found! Place your ships.'
            })
            
            self.send_message(player2_id, {
                'type': 'game_found',
                'player_number': 2,
                'message': 'Game found! Place your ships.'
            })

    def place_ships(self, client_id, ships_data):
        game_id = self.clients[client_id]['game_id']
        if not game_id or game_id not in self.games:
            return
        
        game_info = self.games[game_id]
        game = game_info['game']
        player_number = self.clients[client_id]['player_number']
        
        if player_number == 1:
            player_board = game.player1_board
            player_ships = game.player1_ships
        else:
            player_board = game.player2_board
            player_ships = game.player2_ships
        
        # Clear existing ships
        for row in range(game.board_size):
            for col in range(game.board_size):
                if player_board[row][col] not in ['.', 'X', 'O']:
                    player_board[row][col] = '.'
        player_ships.clear()
        
        # Place new ships
        all_placed = True
        for ship_data in ships_data:
            ship_name = ship_data['name']
            ship_length = game.ships[ship_name]
            start_row = ship_data['start_row']
            start_col = ship_data['start_col']
            orientation = ship_data['orientation']
            
            if not game.place_ship(player_board, player_ships, ship_name, ship_length, start_row, start_col, orientation):
                all_placed = False
                break
        
        if all_placed:
            if player_number == 1:
                game_info['player1_ready'] = True
            else:
                game_info['player2_ready'] = True
            
            self.send_message(client_id, {
                'type': 'ships_placed',
                'success': True,
                'message': 'Ships placed successfully!'
            })
            
            # Check if both players are ready
            if game_info['player1_ready'] and game_info['player2_ready']:
                game_info['game_started'] = True
                self.send_message(game_info['player1'], {
                    'type': 'game_start',
                    'your_turn': True,
                    'message': 'Game started! Your turn to attack.'
                })
                self.send_message(game_info['player2'], {
                    'type': 'game_start',
                    'your_turn': False,
                    'message': 'Game started! Wait for your turn.'
                })
        else:
            self.send_message(client_id, {
                'type': 'ships_placed',
                'success': False,
                'message': 'Failed to place ships. Try again.'
            })

    def attack(self, client_id, row, col):
        game_id = self.clients[client_id]['game_id']
        if not game_id or game_id not in self.games:
            return
        
        game_info = self.games[game_id]
        
        if not game_info['game_started']:
            return
        
        if game_info['current_turn'] != client_id:
            self.send_message(client_id, {
                'type': 'attack_result',
                'success': False,
                'message': 'Not your turn!'
            })
            return
        
        game = game_info['game']
        player_number = self.clients[client_id]['player_number']
        
        if player_number == 1:
            # Player 1 attacks Player 2's board
            opponent_board = game.player2_board
            opponent_ships = game.player2_ships
        else:
            # Player 2 attacks Player 1's board
            opponent_board = game.player1_board
            opponent_ships = game.player1_ships
        
        result = game.attack(opponent_board, opponent_ships, row, col)
        
        # Check for game over
        game_over = self.check_game_over(game_info)
        
        if result in ["Hit", "Miss"] or "Hit and sunk" in result:
            # Switch turns only on miss
            if result == "Miss":
                if game_info['current_turn'] == game_info['player1']:
                    game_info['current_turn'] = game_info['player2']
                else:
                    game_info['current_turn'] = game_info['player1']
            
            # Send attack result to attacker
            self.send_message(client_id, {
                'type': 'attack_result',
                'success': True,
                'result': result,
                'row': row,
                'col': col,
                'your_turn': result != "Miss" and not game_over,
                'game_over': game_over
            })
            
            # Send attack notification to opponent
            opponent_id = game_info['player2'] if player_number == 1 else game_info['player1']
            self.send_message(opponent_id, {
                'type': 'opponent_attack',
                'result': result,
                'row': row,
                'col': col,
                'your_turn': result == "Miss" and not game_over,
                'game_over': game_over
            })
            
            if game_over:
                winner = "Player 1" if player_number == 1 else "Player 2"
                self.send_message(game_info['player1'], {
                    'type': 'game_over',
                    'winner': winner
                })
                self.send_message(game_info['player2'], {
                    'type': 'game_over',
                    'winner': winner
                })
        else:
            self.send_message(client_id, {
                'type': 'attack_result',
                'success': False,
                'message': result
            })

    def check_game_over(self, game_info):
        game = game_info['game']
        
        # Check if all ships of player 1 are sunk
        all_sunk_player1 = True
        for ship_name, positions in game.player1_ships.items():
            for r, c in positions:
                if game.player1_board[r][c] != 'X':
                    all_sunk_player1 = False
                    break
            if not all_sunk_player1:
                break
        
        # Check if all ships of player 2 are sunk
        all_sunk_player2 = True
        for ship_name, positions in game.player2_ships.items():
            for r, c in positions:
                if game.player2_board[r][c] != 'X':
                    all_sunk_player2 = False
                    break
            if not all_sunk_player2:
                break
        
        return all_sunk_player1 or all_sunk_player2

    def send_game_state(self, client_id):
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

    def send_message(self, client_id, message):
        if client_id in self.clients:
            try:
                self.clients[client_id]['socket'].send(json.dumps(message).encode('utf-8'))
            except:
                self.disconnect_client(client_id)

    def disconnect_client(self, client_id):
        if client_id in self.clients:
            client_socket = self.clients[client_id]['socket']
            client_socket.close()
            
            # Remove from waiting players if present
            if client_id in self.waiting_players:
                self.waiting_players.remove(client_id)
            
            # Handle game cleanup
            game_id = self.clients[client_id].get('game_id')
            if game_id and game_id in self.games:
                game_info = self.games[game_id]
                opponent_id = None
                
                if game_info['player1'] == client_id:
                    opponent_id = game_info['player2']
                elif game_info['player2'] == client_id:
                    opponent_id = game_info['player1']
                
                if opponent_id:
                    self.send_message(opponent_id, {
                        'type': 'opponent_disconnected',
                        'message': 'Your opponent has disconnected.'
                    })
                
                del self.games[game_id]
            
            del self.clients[client_id]
            print(f"Client {client_id} disconnected")

if __name__ == '__main__':
    server = BattleshipServer('0.0.0.0', 8888)
    server.start()

