/**
 * Form input validation (Zod). This only guards user input before it is sent;
 * the backend re-validates everything and remains the source of truth.
 */
import { z } from "zod";

const requiredText = (label: string, max = 50_000) =>
  z
    .string()
    .max(max, `${label} is too long`)
    .refine((v) => v.trim().length > 0, `${label} is required`);

const weight = z
  .number({ error: "Enter a number" })
  .min(0, "Weight cannot be negative")
  .max(100, "Weight must be 100 or less");

export const projectFormSchema = z.object({
  name: requiredText("Name", 200),
  description: z.string().max(5_000),
});
export type ProjectFormValues = z.infer<typeof projectFormSchema>;

export const criterionFormSchema = z
  .object({
    name: requiredText("Name", 200),
    description: z.string().max(5_000),
    weight,
    scale_min: z.number({ error: "Enter a number" }).int("Must be a whole number").min(0).max(100),
    scale_max: z.number({ error: "Enter a number" }).int("Must be a whole number").min(0).max(100),
    enabled: z.boolean(),
  })
  .refine((v) => v.scale_min < v.scale_max, {
    message: "Scale max must be greater than scale min",
    path: ["scale_max"],
  });
export type CriterionFormValues = z.infer<typeof criterionFormSchema>;

export const evaluationFormSchema = z
  .object({
    project_id: z.string().min(1, "Choose a project"),
    title: requiredText("Title", 300),
    prompt: requiredText("Prompt"),
    response_a: requiredText("Response A"),
    response_b: requiredText("Response B"),
    criteria: z.array(
      z.object({
        criterion_id: z.string(),
        selected: z.boolean(),
        weight,
      }),
    ),
  })
  .superRefine((v, ctx) => {
    const selected = v.criteria.filter((c) => c.selected);
    if (selected.length === 0) {
      ctx.addIssue({ code: "custom", message: "Select at least one criterion", path: ["criteria"] });
    } else if (selected.every((c) => c.weight === 0)) {
      ctx.addIssue({
        code: "custom",
        message: "At least one selected criterion needs a weight above 0",
        path: ["criteria"],
      });
    }
  });
export type EvaluationFormValues = z.infer<typeof evaluationFormSchema>;
