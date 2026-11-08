const EMBEDDING_MODEL_PREFIXES = [
  'all-minilm',
  'bge-',
  'bge_',
  'e5-',
  'e5_',
  'gte-',
  'gte_',
  'jina-embeddings',
  'nomic-bert',
  'sentence-transformers',
];

export function isEmbedOnlyModel(modelId: string): boolean {
  const name = (modelId || '').trim().toLowerCase();
  const leaf = name.slice(name.lastIndexOf('/') + 1).split(':')[0];
  return (
    leaf.includes('embed') ||
    leaf.includes('minilm') ||
    EMBEDDING_MODEL_PREFIXES.some((prefix) => leaf.startsWith(prefix))
  );
}

/** Parameter count in billions from a model id like `qwen3.5:4b`, if it names one. */
export function modelSizeBillions(modelId: string): number | null {
  const name = (modelId || '').trim().toLowerCase();
  const match = name.match(/(?:^|[:\-_/])(\d+(?:\.\d+)?)b(?=$|[-_.:])/);
  return match ? Number(match[1]) : null;
}

/** Models below about 4B parameters often miss or garble tool calls. */
export function isSmallForAgent(modelId: string): boolean {
  const size = modelSizeBillions(modelId);
  return size !== null && size < 4;
}
