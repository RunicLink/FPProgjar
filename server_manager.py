import socket
import threading
import hashlib

BACKEND_SERVERS = [
    ("127.0.0.1", 8889),
    ("127.0.0.1", 8890),
    ("127.0.0.1", 8891)
]

sticky_sessions = {}
sticky_lock = threading.Lock()

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
            except (ConnectionResetError, BrokenPipeError, socket.error):
                pass
            except Exception as e:
                print(f"Error forwarding data: {e}")
            finally:
                src.close()
                dst.close()

        threading.Thread(target=forward, args=(client_sock, backend_sock), daemon=True).start()
        threading.Thread(target=forward, args=(backend_sock, client_sock), daemon=True).start()

    except Exception as e:
        print(f"Error connecting to backend {target_host}:{target_port} - {e}")
        client_sock.close()

def get_sticky_server_index(client_ip):
    ip_hash = int(hashlib.sha1(client_ip.encode('utf-8')).hexdigest(), 16)
    return ip_hash % len(BACKEND_SERVERS)

def load_balancer():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("0.0.0.0", LISTEN_PORT))
    server_socket.listen(100)
    print(f"[Load Balancer] Listening on port {LISTEN_PORT}")

    while True:
        client_sock, addr = server_socket.accept()
        client_ip = addr[0]
        print(f"[Load Balancer] Connection from {addr}")

        with sticky_lock:
            if client_ip in sticky_sessions:
                target_server_index = sticky_sessions[client_ip]
                if target_server_index >= len(BACKEND_SERVERS):
                    target_server_index = get_sticky_server_index(client_ip)
                    sticky_sessions[client_ip] = target_server_index
            else:
                target_server_index = get_sticky_server_index(client_ip)
                sticky_sessions[client_ip] = target_server_index

            target_host, target_port = BACKEND_SERVERS[target_server_index]

        print(f"[Load Balancer] Routing {client_ip} to backend {target_host}:{target_port} (index: {target_server_index})")
        threading.Thread(target=handle_client, args=(client_sock, target_host, target_port), daemon=True).start()

if __name__ == "__main__":
    load_balancer()
    