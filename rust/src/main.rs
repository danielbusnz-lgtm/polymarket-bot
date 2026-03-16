use tonic::{transport::Server, Request, Response, Status};

// include the auto-generated proto code
pub mod trader {
    tonic::include_proto!("trader");
}

use trader::trader_server::{Trader, TraderServer};
use trader::{OrderRequest, OrderResponse};

// our server struct
#[derive(Default)]
pub struct TraderService;

#[tonic::async_trait]
impl Trader for TraderService {
    async fn place_order(
        &self,
        request: Request<OrderRequest>,
    ) -> Result<Response<OrderResponse>, Status> {
        let order = request.into_inner();

        println!(
            "Received order: {} {} @ {} size ${} via {}",
            order.outcome, order.market_id, order.price, order.size, order.strategy
        );

        let response = OrderResponse {
            success: true,
            order_id: "test-order-001".to_string(),
            message: format!("Order received for {}", order.market_id),
        };

        Ok(Response::new(response))
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let addr = "0.0.0.0:50051".parse()?;
    println!("Trader gRPC server listening on {}", addr);

    Server::builder()
        .add_service(TraderServer::new(TraderService::default()))
        .serve(addr)
        .await?;

    Ok(())
}
