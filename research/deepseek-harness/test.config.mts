import { defineConfig } from "../repos/deepseek-harness/node_modules/vitest/dist/config.js";
import ts from "../repos/deepseek-harness/node_modules/typescript/lib/typescript.js";
import { standardDecoratorPlugin } from "../repos/deepseek-harness/vitest.shared.ts";
import { resolve } from "node:path";
const repo=resolve(import.meta.dirname,"../repos/deepseek-harness");
const conf=ts.readConfigFile(resolve(repo,"tsconfig.base.json"),ts.sys.readFile).config;
const alias=Object.entries(conf.compilerOptions.paths).filter(([k])=>!k.includes("*")).map(([find,paths])=>({find,replacement:resolve(repo,paths[0])}));
export default defineConfig({plugins:[standardDecoratorPlugin()],resolve:{alias},test:{
 include:[resolve(import.meta.dirname,"experiment.spec.ts")],environment:"node",testTimeout:45000,hookTimeout:15000,maxWorkers:1, fileParallelism:false
}});
