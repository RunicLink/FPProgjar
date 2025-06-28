import socket
import json
import threading

class BattleshipClient:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False
        self.game_state = {
            'own_board': None,
            'opponent_board': None,
            'your_turn': False,
            'game_started': False,
            'player_number': None
        }
        self.message_callbacks = []

    def connect(self):
        try:
            self.socket.connect((self.host, self.port))
            self.connected = True
            
            # Start listening for messages
            listen_thread = threading.Thread(target=self.listen_for_messages)
            listen_thread.daemon = True
            listen_thread.start()
            
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False

    def listen_for_messages(self):
        while self.connected:
            try:
                data = self.socket.recv(1024).decode('utf-8')
                if not data:
                    break
                
                message = json.loads(data)
                self.handle_message(message)
                
            except Exception as e:
                print(f"Error receiving message: {e}")
                break
        
        self.connected = False

    def handle_message(self, message):
        msg_type = message.get('type')
        
        if msg_type == 'game_found':
            self.game_state['player_number'] = message['player_number']
        elif msg_type == 'game_state':
            self.game_state['own_board'] = message['own_board']
            self.game_state['opponent_board'] = message['opponent_board']
            self.game_state['your_turn'] = message['your_turn']
            self.game_state['game_started'] = message['game_started']
        elif msg_type == 'game_start':
            self.game_state['your_turn'] = message['your_turn']
            self.game_state['game_started'] = True
        elif msg_type == 'attack_result':
            if message['success']:
                self.game_state['your_turn'] = message.get('your_turn', False)
        elif msg_type == 'opponent_attack':
            self.game_state['your_turn'] = message.get('your_turn', False)
        
        # Call registered callbacks
        for callback in self.message_callbacks:
            callback(message)

    def add_message_callback(self, callback):
        self.message_callbacks.append(callback)

    def send_message(self, message):
        if self.connected:
            try:
                self.socket.send(json.dumps(message).encode('utf-8'))
                return True
            except Exception as e:
                print(f"Failed to send message: {e}")
                return False
        return False

    def join_game(self):
        return self.send_message({'type': 'join_game'})

    def place_ships(self, ships_data):
        return self.send_message({
            'type': 'place_ships',
            'ships': ships_data
        })

    def attack(self, row, col):
        return self.send_message({
            'type': 'attack',
            'row': row,
            'col': col
        })

    def get_game_state(self):
        return self.send_message({'type': 'get_game_state'})

    def disconnect(self):
        self.connected = False
        if self.socket:
            self.socket.close()

if __name__ == '__main__':
    # Simple test client
    client = BattleshipClient()
    
    def message_handler(message):
        print(f"Received: {message}")
    
    client.add_message_callback(message_handler)
    
    if client.connect():
        print("Connected to server")
        client.join_game()
        
        # Keep the client running
        try:
            while client.connected:
                pass
        except KeyboardInterrupt:
            print("Disconnecting...")
            client.disconnect()
    else:
        print("Failed to connect to server")

