fn main() {
    tonic_build::compile_protos("../proto/trader.proto")
        .expect("Failed to compile proto");
}
