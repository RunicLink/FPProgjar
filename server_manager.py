import socket
import threading

BACKEND_SERVERS = [
    ("127.0.0.1", 8889),
    ("127.0.0.1", 8890),
    ("127.0.0.1", 8891)
]

current_server = 0
lock = threading.Lock()
LISTEN_PORT = 8888 

def handle_client(client_sock, target_host, target_port):
    try:
        backend_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        backend_sock.connect((target_host, target_port))

        def forward(src, dst):
            try:
                while True:
                    data = src.recv(4096)
                    if not data:
                        break
                    dst.sendall(data)
            except:
                pass
            finally:
                src.close()
                dst.close()

        threading.Thread(target=forward, args=(client_sock, backend_sock)).start()
        threading.Thread(target=forward, args=(backend_sock, client_sock)).start()

    except Exception as e:
        print(f"Error connecting to backend {target_host}:{target_port} - {e}")
        client_sock.close()

def load_balancer():
    global current_server

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("0.0.0.0", LISTEN_PORT))
    server_socket.listen(100)
    print(f"[Load Balancer] Listening on port {LISTEN_PORT}")

    while True:
        client_sock, addr = server_socket.accept()
        print(f"[Load Balancer] Connection from {addr}")

        with lock:
            target_host, target_port = BACKEND_SERVERS[current_server]
            current_server = (current_server + 1) % len(BACKEND_SERVERS)

        threading.Thread(target=handle_client, args=(client_sock, target_host, target_port)).start()

if __name__ == "__main__":
    load_balancer()
