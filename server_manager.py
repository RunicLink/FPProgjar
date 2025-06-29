import asyncio
import hashlib

BACKEND_SERVERS = [
    ("127.0.0.1", 8889),
    ("127.0.0.1", 8890),
    ("127.0.0.1", 8891)
]

sticky_sessions = {}

LISTEN_PORT = 8888
HOST = "0.0.0.0"

def get_sticky_server_index(client_ip):
    ip_hash = int(hashlib.sha1(client_ip.encode('utf-8')).hexdigest(), 16)
    return ip_hash % len(BACKEND_SERVERS)

async def forward(reader, writer):
    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            
            writer.write(data)
            await writer.drain()
    except asyncio.CancelledError:
        pass
    finally:
        writer.close()
        await writer.wait_closed()

async def handle_client(client_reader, client_writer):
    client_addr = client_writer.get_extra_info('peername')
    client_ip = client_addr[0]
    print(f"[LB-async] Connection from {client_addr}")

    if client_ip in sticky_sessions:
        target_server_index = sticky_sessions[client_ip]
    else:
        target_server_index = get_sticky_server_index(client_ip)
        sticky_sessions[client_ip] = target_server_index
    
    target_host, target_port = BACKEND_SERVERS[target_server_index]

    try:
        backend_reader, backend_writer = await asyncio.open_connection(
            target_host, target_port)
    except Exception as e:
        print(f"[LB-async] Error connecting to backend {target_host}:{target_port} - {e}")
        client_writer.close()
        await client_writer.wait_closed()
        return

    print(f"[LB-async] Routing {client_ip} to backend {target_host}:{target_port}")

    client_to_backend = asyncio.create_task(
        forward(client_reader, backend_writer))
    
    backend_to_client = asyncio.create_task(
        forward(backend_reader, client_writer))

    done, pending = await asyncio.wait(
        [client_to_backend, backend_to_client],
        return_when=asyncio.FIRST_COMPLETED
    )

    for task in pending:
        task.cancel()

async def main():
    print(f"[LB-async] Starting server on port {LISTEN_PORT}")
    
    server = await asyncio.start_server(
        handle_client, HOST, LISTEN_PORT)

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[LB-async] Server shutting down.")