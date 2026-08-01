import Link from "next/link";

import { CreateAccountForm, type AccountField } from "@/components/admin/create-account-form";
import { Icon } from "@/components/ui/icon";

export const metadata = { title: "Create a company" };

const FIELDS: readonly AccountField[] = [
  { id: "legal_name", label: "Company name", required: true },
  { id: "email", label: "Email", type: "email", required: true, autoComplete: "email" },
  {
    id: "registration_number",
    label: "Registration / PAN number",
    required: true,
    help: "Checked against existing employers — one number, one organisation.",
  },
  { id: "contact_person", label: "HR contact name", autoComplete: "name" },
  { id: "phone", label: "Phone number", type: "tel", autoComplete: "tel" },
  { id: "website", label: "Website", type: "url", placeholder: "https://" },
  { id: "address", label: "Address", wide: true, placeholder: "Municipality, district" },
];

export default function CreateCompanyPage() {
  return (
    <div className="mx-auto w-full max-w-2xl">
      <Link
        href="/admin"
        className="inline-flex items-center gap-1 text-xs font-medium text-text-muted hover:text-text"
      >
        <Icon name="chevron-right" size={12} className="rotate-180" />
        Back
      </Link>
      <h1 className="mt-2 text-lg font-semibold tracking-tight">Create a company</h1>
      <p className="mt-1.5 max-w-lg text-sm text-text-muted">
        This sets up their employer dashboard — checking candidate validity and issuing
        experience letters. New companies start on the free plan.
      </p>

      <CreateAccountForm
        target="organization"
        fixedValues={{ kind: "EMPLOYER" }}
        fields={FIELDS}
        backHref="/admin"
        successNote="Their employer dashboard is ready on the free plan, with unlimited experience-letter issuing."
      />
    </div>
  );
}
