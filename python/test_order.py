import grpc
import sys
sys.path.insert(0, '.')
from proto import trader_pb2, trader_pb2_grpc

channel = grpc.insecure_channel('localhost:50051')
stub = trader_pb2_grpc.TraderStub(channel)

response = stub.PlaceOrder(trader_pb2.OrderRequest(
    market_id="test-market-123",
    outcome="YES",
    price=0.65,
    size=20.0,
    strategy="llm",
    tick_size=0.01,
    neg_risk=False,
))

print("Success:", response.success)
print("Order ID:", response.order_id)
print("Message:", response.message)
