use futures_util::{SinkExt, StreamExt};
use serde::Deserialize;
use tokio::sync::mpsc;
use tokio_tungstenite::{connect_async, tungstenite::Message};

#[derive(Debug, Deserialize)]
pub struct PriceLevel {
    pub price: String,
    pub size: String,
}

#[derive(Debug, Deserialize)]
pub struct BookSnapshot {
    pub asset_id: String,
    pub bids: Vec<PriceLevel>,
    pub asks: Vec<PriceLevel>,
    #[serde(rename = "type")]
    pub event_type: String,
}

pub async fn subscribe(token_id: &str, tx: mpsc::Sender<BookSnapshot>) {
    let url = "wss://ws-subscriptions-clob.polymarket.com/ws/market";
    let (ws_stream, _) = connect_async(url).await.expect("Failed to connect");
    let (mut write, mut read) = ws_stream.split();

    let sub = serde_json::json!({
        "assets_ids": [token_id],
        "type": "market"
    });
    write.send(Message::Text(sub.to_string().into())).await.expect("Failed to subscribe");

    while let Some(Ok(Message::Text(text))) = read.next().await {
        if let Ok(snapshot) = serde_json::from_str::<BookSnapshot>(&text) {
            if snapshot.event_type == "book" {
                let _ = tx.send(snapshot).await;
            }
        }
    }
}
