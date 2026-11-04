import { stopApi, stopWeb } from "./servers";

export default async function globalTeardown() {
  stopWeb();
  await stopApi();
}
