import FeatureWorkspace from "@/components/FeatureWorkspace";
import { getGenerationSummary } from "@/lib/server/generation-config";

export default function Home() {
  return <FeatureWorkspace generation={getGenerationSummary()} />;
}
