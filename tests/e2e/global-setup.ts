import { buildWeb, resetData, startApi, startWeb, stopApi, stopWeb } from "./servers";

export default async function globalSetup() {
  stopWeb();
  await stopApi();
  resetData(); // fresh DB + real sandbox validation of all content
  if (!process.env.E2E_SKIP_BUILD) buildWeb();
  await startApi();
  await startWeb();
}
