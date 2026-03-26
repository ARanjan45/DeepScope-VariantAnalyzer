import modal
from pydantic import BaseModel


class VariantRequest(BaseModel):
    variant_position: int
    alternative: str
    genome: str
    chromosome: str


# Uses official EVO2 light install method via conda (pre-built binaries, no compilation)
evo2_image = (
    modal.Image.from_registry(
        "nvcr.io/nvidia/pytorch:25.01-py3",
    )
    .apt_install(["git", "cmake", "ninja-build", "build-essential"])
    # Uninstall whatever flash-attn came with the NGC container
    .run_commands(
        "pip uninstall flash-attn -y || true"
    )
    # Install flash-attn 2.8.3 from mjun0812 (2.x API, compatible with vortex)
    # cu128 + torch2.7 + abi3 (Python 3.9+)
    .run_commands(
        "pip install https://github.com/mjun0812/flash-attention-prebuild-wheels/releases/download/v0.7.16/flash_attn-2.8.3+cu128torch2.7-cp312-cp312-linux_x86_64.whl"
    )
    .run_commands(
        "pip install evo2"
    )
    .pip_install([
        "fastapi[standard]",
        "matplotlib", "pandas", "seaborn",
        "scikit-learn", "openpyxl", "biopython",
        "requests", "pydantic", "huggingface_hub",
    ])
)

app = modal.App("genome-analysis-v2", image=evo2_image)

volume = modal.Volume.from_name("hf_cache", create_if_missing=True)
mount_path = "/root/.cache/huggingface"


def get_genome_sequence(position, genome: str, chromosome: str, window_size=8192):
    import requests

    half_window = window_size // 2
    start = max(0, position - 1 - half_window)
    end = position - 1 + half_window + 1

    print(f"Fetching {window_size}bp window around position {position} from UCSC API..")
    print(f"Coordinates: {chromosome}:{start}-{end} ({genome})")

    api_url = f"https://api.genome.ucsc.edu/getData/sequence?genome={genome};chrom={chromosome};start={start};end={end}"
    response = requests.get(api_url)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch genome sequence: {response.status_code}")

    genome_data = response.json()
    if "dna" not in genome_data:
        raise Exception(f"UCSC API error: {genome_data.get('error', 'Unknown')}")

    sequence = genome_data.get("dna", "").upper()
    print(f"Loaded reference genome sequence window (length: {len(sequence)} bases)")
    return sequence, start


def analyze_variant(relative_pos_in_window, reference, alternative, window_seq, model):
    var_seq = (
        window_seq[:relative_pos_in_window]
        + alternative
        + window_seq[relative_pos_in_window + 1:]
    )

    ref_score = model.score_sequences([window_seq])[0]
    var_score = model.score_sequences([var_seq])[0]
    delta_score = var_score - ref_score

    threshold = -0.0009178519
    lof_std = 0.0015140239
    func_std = 0.0009016589

    if delta_score < threshold:
        prediction = "Likely pathogenic"
        confidence = min(1.0, abs(delta_score - threshold) / lof_std)
    else:
        prediction = "Likely benign"
        confidence = min(1.0, abs(delta_score - threshold) / func_std)

    return {
        "reference": reference,
        "alternative": alternative,
        "delta_score": float(delta_score),
        "prediction": prediction,
        "classification_confidence": float(confidence),
    }


@app.cls(
    gpu="H100",
    volumes={mount_path: volume},
    secrets=[modal.Secret.from_name("huggingface-secret")],
    max_containers=3,
    retries=2,
    scaledown_window=120,
)
class Evo2Model:
    @modal.enter()
    def load_evo2_model(self):
        import torch
        from evo2 import Evo2
        from transformer_engine.common.recipe import _OverrideLinearPrecision
        
        # Register transformer_engine globals so torch can safely unpickle the weights
        torch.serialization.add_safe_globals([_OverrideLinearPrecision])
        
        print("Loading evo2 model...")
        self.model = Evo2("evo2_7b")
    print("Evo2 model loaded")

    @modal.fastapi_endpoint(method="POST")
    def analyze_single_variant(self, request: VariantRequest):
        variant_position = request.variant_position
        alternative = request.alternative
        genome = request.genome
        chromosome = request.chromosome

        print(f"Genome: {genome}, Chromosome: {chromosome}")
        print(f"Position: {variant_position}, Alternative: {alternative}")

        WINDOW_SIZE = 8192
        window_seq, seq_start = get_genome_sequence(
            position=variant_position,
            genome=genome,
            chromosome=chromosome,
            window_size=WINDOW_SIZE,
        )

        relative_pos = variant_position - 1 - seq_start
        print(f"Relative position within window: {relative_pos}")

        if relative_pos < 0 or relative_pos >= len(window_seq):
            raise ValueError(
                f"Variant position {variant_position} is outside the fetched window"
            )

        reference = window_seq[relative_pos]
        print(f"Reference base: {reference}")

        result = analyze_variant(
            relative_pos_in_window=relative_pos,
            reference=reference,
            alternative=alternative,
            window_seq=window_seq,
            model=self.model,
        )
        result["position"] = variant_position
        return result




@app.local_entrypoint()
def main():
    import requests

    url = "https://aranjan45--genome-analysis-v2-evo2model-analyze-sing-ce2704-dev.modal.run"

    payload = {
        "variant_position": 43119628,
        "alternative": "G",
        "genome": "hg38",
        "chromosome": "chr17",
    }

    response = requests.post(
        url, json=payload, headers={"Content-Type": "application/json"}
    )
    response.raise_for_status()
    print(response.json())