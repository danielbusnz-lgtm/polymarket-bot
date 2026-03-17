mod executor;
mod ws;

use std::sync::Arc;

use tonic::{transport::Server, Request, Response, Status};

pub mod trader {
    tonic::include_proto!("trader");
}

use trader::trader_server::{Trader, TraderServer};
use trader::{OrderRequest, OrderResponse};

use executor::{Executor, SIDE_BUY, SIDE_SELL};

pub struct TraderService {
    executor: Arc<Executor>,
}

#[tonic::async_trait]
impl Trader for TraderService {
    async fn place_order(
        &self,
        request: Request<OrderRequest>,
    ) -> Result<Response<OrderResponse>, Status> {
        let req = request.into_inner();

        // The proto gives us a market_id (conditionId) and outcome ("YES"/"NO").
        // Polymarket's CLOB works on token IDs, not condition IDs — for now we
        // treat market_id as the token_id.  The Python side should resolve the
        // correct token_id before calling us.
        let token_id = &req.market_id;
        let side     = if req.outcome == "YES" { SIDE_BUY } else { SIDE_SELL };
        let price    = req.price;
        let size     = req.size;

        println!(
            "[executor] {} {} @ {:.3}  size=${:.2}  strategy={}",
            req.outcome, token_id, price, size, req.strategy
        );

        match self.executor.place_order(token_id, side, price, size).await {
            Ok(order_id) => {
                println!("[executor] ✓ order placed: {order_id}");
                Ok(Response::new(OrderResponse {
                    success:  true,
                    order_id: order_id.clone(),
                    message:  format!("Order placed: {order_id}"),
                }))
            }
            Err(e) => {
                eprintln!("[executor] ✗ order failed: {e}");
                Ok(Response::new(OrderResponse {
                    success:  false,
                    order_id: String::new(),
                    message:  e.to_string(),
                }))
            }
        }
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Load .env so PRIVATE_KEY and API credentials are available
    dotenvy::dotenv().ok();

    let exec = Executor::from_env().expect(
        "Missing credentials. Set PRIVATE_KEY, POLYMARKET_API_KEY, \
         POLYMARKET_SECRET, POLYMARKET_PASSPHRASE in .env"
    );

    let addr = "0.0.0.0:50051".parse()?;
    println!("[server] gRPC listening on {addr}");

    Server::builder()
        .add_service(TraderServer::new(TraderService {
            executor: Arc::new(exec),
        }))
        .serve(addr)
        .await?;

    Ok(())
}
