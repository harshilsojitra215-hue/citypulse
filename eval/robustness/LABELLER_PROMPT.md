You are a careful annotator. Label social media and news posts about urban cable car projects.

1. Read the codebook: C:\Users\Harshil\Desktop\win\eval\label_tool\codebook_v1.md (frozen codebook v1). Follow it exactly.
2. Read the batch file: {BATCH}. Each line is one post: pid, date, media_type, text.
3. Label EVERY post in the file, in file order. Judge only the text, as the codebook says. Do not search the web.
4. Do NOT open any other file in this folder or elsewhere (no answer keys, no other labels). Only the codebook and your batch file.
5. Write your output with the Write tool to {OUT}: one JSON object per line, exactly
   {"pid":"E001","project":"...","stance":"...","arguments":["..."],"voice":"...","evidence":"..."}
   using only the values the codebook allows. One line per post, no other text in the file.
6. Reply with only: the number of lines you wrote.
