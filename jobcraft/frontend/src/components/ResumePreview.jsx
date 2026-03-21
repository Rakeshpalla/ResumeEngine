export default function ResumePreview({ resume }) {
  if (!resume) {
    return (
      <div className="rounded-xl border border-border bg-bg-card p-6 text-center text-text-secondary">
        No tailored resume available.
      </div>
    );
  }

  return (
    <div className="space-y-6 rounded-xl border border-border bg-bg-card p-6">
      {resume.summary && (
        <div>
          <h3 className="mb-2 font-[family-name:var(--font-display)] text-sm font-semibold uppercase tracking-wider text-primary">
            Summary
          </h3>
          <p className="text-sm leading-relaxed text-text-primary">{resume.summary}</p>
        </div>
      )}

      {resume.experience?.length > 0 && (
        <div>
          <h3 className="mb-3 font-[family-name:var(--font-display)] text-sm font-semibold uppercase tracking-wider text-primary">
            Experience
          </h3>
          <div className="space-y-4">
            {resume.experience.map((exp, i) => (
              <div key={i} className="border-l-2 border-border pl-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h4 className="text-sm font-semibold text-text-primary">{exp.role}</h4>
                  <span className="text-xs text-text-secondary">{exp.dates}</span>
                </div>
                <p className="mb-2 text-xs text-text-secondary">{exp.company}</p>
                <ul className="space-y-1">
                  {exp.bullets?.map((bullet, j) => (
                    <li key={j} className="flex gap-2 text-sm text-text-primary/90">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary" />
                      <span>{bullet}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      {resume.skills?.length > 0 && (
        <div>
          <h3 className="mb-2 font-[family-name:var(--font-display)] text-sm font-semibold uppercase tracking-wider text-primary">
            Skills
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {resume.skills.map((skill, i) => (
              <span
                key={i}
                className="rounded-md bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary"
              >
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      {resume.education?.length > 0 && (
        <div>
          <h3 className="mb-2 font-[family-name:var(--font-display)] text-sm font-semibold uppercase tracking-wider text-primary">
            Education
          </h3>
          {resume.education.map((edu, i) => (
            <div key={i} className="text-sm text-text-primary">
              <span className="font-medium">{edu.degree}</span>
              {edu.school && <span className="text-text-secondary"> — {edu.school}</span>}
              {edu.year && <span className="text-text-secondary"> ({edu.year})</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
