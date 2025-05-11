from discord.ext import commands
import discord
from discord import Embed
from database import cursor, insert_pdf
from config import ALLOWED_LANGUAGES, ALLOWED_CATEGORIES, CATEGORY_SUBCATEGORIES, PDF_CHANNEL_ID
from utils.file_utils import get_file_hash, delete_after_delay
import traceback

class PDFMetadataModal(discord.ui.Modal):
    def __init__(self, file_info, categories, subcategories, languages):
        print(f"[DEBUG] Creating modal for file: {file_info['filename']}")
        # Use a shorter title to stay within Discord's limits
        super().__init__(title="PDF Metadata")
        self.file_info = file_info
        self.categories = categories
        
        # Add input fields
        self.title_input = discord.ui.TextInput(
            label="Title",
            placeholder="Enter the title of the PDF",
            required=True
        )
        self.add_item(self.title_input)
        
        self.author_input = discord.ui.TextInput(
            label="Author",
            placeholder="Enter the author's name",
            required=True
        )
        self.add_item(self.author_input)
        
        # Limit the category placeholder length
        # Instead of listing all categories, just mention checking the docs
        self.category_input = discord.ui.TextInput(
            label="Category",
            placeholder="Enter a valid category (check server documentation for options)",
            required=True
        )
        self.add_item(self.category_input)
        
        self.subcategory_input = discord.ui.TextInput(
            label="Subcategory",
            placeholder="Enter the appropriate subcategory for the selected category",
            required=True
        )
        self.add_item(self.subcategory_input)
        
        # Limit the language placeholder length
        # Just show a few examples instead of the full list
        language_examples = languages[:5] if len(languages) > 5 else languages
        self.language_input = discord.ui.TextInput(
            label="Language Code",
            placeholder=f"Examples: {', '.join(language_examples)}...",
            required=True,
            max_length=5
        )
        self.add_item(self.language_input)
        print(f"[DEBUG] Modal created successfully")
    
    async def on_submit(self, interaction: discord.Interaction):
        print(f"[DEBUG] Modal submitted by user: {interaction.user}")
        print(f"[DEBUG] Title: {self.title_input.value}")
        print(f"[DEBUG] Author: {self.author_input.value}")
        print(f"[DEBUG] Category: {self.category_input.value}")
        print(f"[DEBUG] Subcategory: {self.subcategory_input.value}")
        print(f"[DEBUG] Language: {self.language_input.value}")
        
        # Validate inputs
        category = self.category_input.value
        if category not in self.categories:
            print(f"[DEBUG] Invalid category: {category}")
            await interaction.response.send_message(
                f"❌ Invalid category. Please choose from: {', '.join(self.categories)}", 
                ephemeral=True
            )
            return
        
        subcategory = self.subcategory_input.value
        if subcategory not in CATEGORY_SUBCATEGORIES.get(category, []):
            print(f"[DEBUG] Invalid subcategory: {subcategory} for category: {category}")
            await interaction.response.send_message(
                f"❌ Invalid subcategory for {category}. Please choose a valid subcategory.", 
                ephemeral=True
            )
            return
        
        language = self.language_input.value
        if language not in ALLOWED_LANGUAGES:
            print(f"[DEBUG] Invalid language: {language}")
            await interaction.response.send_message(
                f"❌ Invalid language code. Choose from: {', '.join(ALLOWED_LANGUAGES)}", 
                ephemeral=True
            )
            return
        
        # Save the metadata
        data = {
            "title": self.title_input.value,
            "author": self.author_input.value,
            "category": category,
            "subcategory": subcategory,
            "language": language,
            "file_hash": self.file_info["file_hash"],
            "message_id": self.file_info["message_id"],
            "channel_id": self.file_info["channel_id"],
            "user_id": self.file_info["user_id"],
            "username": self.file_info["username"]
        }
        
        try:
            print(f"[DEBUG] Inserting PDF data into database: {data}")
            insert_pdf(data)
            print(f"[DEBUG] PDF data inserted successfully")
        except Exception as e:
            print(f"[ERROR] Failed to insert PDF data: {e}")
            print(traceback.format_exc())
            await interaction.response.send_message(
                f"❌ Error saving PDF metadata: {str(e)}", 
                ephemeral=True
            )
            return
        
        # Send confirmation
        try:
            embed = Embed(
                title="✅ PDF Added Successfully",
                description=f"**{data['title']}** by *{data['author']}*",
                color=discord.Color.green()
            )
            embed.add_field(name="Category", value=f"{data['category']} > {data['subcategory']}", inline=True)
            embed.add_field(name="Language", value=data['language'], inline=True)
            
            print(f"[DEBUG] Sending confirmation embed to user")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"[ERROR] Failed to send confirmation: {e}")
            print(traceback.format_exc())
        
        # React to the original message
        try:
            print(f"[DEBUG] Attempting to add reaction to original message")
            channel = interaction.client.get_channel(self.file_info["channel_id"])
            print(f"[DEBUG] Got channel: {channel}")
            message = await channel.fetch_message(self.file_info["message_id"])
            print(f"[DEBUG] Got message: {message.id}")
            await message.add_reaction("✅")
            print(f"[DEBUG] Reaction added successfully")
        except Exception as e:
            print(f"[ERROR] Error adding reaction: {e}")
            print(traceback.format_exc())


class PDFUpload(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print(f"[DEBUG] PDFUpload cog initialized")

    # Send category info in the initial message
    async def send_category_guide(self, message):
        """Send a guide with allowed categories and subcategories"""
        embed = Embed(
            title="📚 PDF Category Guide",
            description="Use these categories and subcategories when adding metadata:",
            color=discord.Color.blue()
        )
        
        for category in ALLOWED_CATEGORIES:
            subcats = CATEGORY_SUBCATEGORIES.get(category, [])
            if subcats:
                # Show only first 3 subcategories if there are many
                if len(subcats) > 3:
                    subcat_text = f"{', '.join(subcats[:3])}... and more"
                else:
                    subcat_text = ', '.join(subcats)
                embed.add_field(name=category, value=subcat_text, inline=False)
        
        return await message.channel.send(embed=embed, reference=message)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for PDF uploads and process them"""
        print(f"[DEBUG] Message received in channel: {message.channel.id}")
        
        if message.channel.id != PDF_CHANNEL_ID:
            return
        
        print(f"[DEBUG] Message is in PDF channel from user: {message.author}")
        
        if message.author.bot:
            print(f"[DEBUG] Ignoring message from bot")
            return
        
        pdf_attachments = [a for a in message.attachments if a.filename.lower().endswith('.pdf')]
        print(f"[DEBUG] Found {len(pdf_attachments)} PDF attachments")
        
        if not pdf_attachments:
            return
        
        # Send category guide first
        category_guide = await self.send_category_guide(message)
        
        for attachment in pdf_attachments:
            print(f"[DEBUG] Processing attachment: {attachment.filename}")
            file_info = {
                "filename": attachment.filename,
                "url": attachment.url,
                "size": attachment.size,
                "message_id": message.id,
                "channel_id": message.channel.id,
                "user_id": message.author.id,
                "username": str(message.author)
            }
            
            try:
                print(f"[DEBUG] Getting file hash for: {attachment.filename}")
                file_hash = await get_file_hash(attachment)
                file_info["file_hash"] = file_hash
                print(f"[DEBUG] File hash: {file_hash}")
                
                print(f"[DEBUG] Checking for duplicates")
                cursor.execute("SELECT title, author FROM pdfs WHERE file_hash = ?", (file_hash,))
                existing = cursor.fetchone()
                
                if existing:
                    title, author = existing
                    print(f"[DEBUG] Duplicate detected: {title} by {author}")
                    embed = Embed(
                        title="⚠️ Duplicate Detected",
                        description=f"This file appears to be a duplicate of **{title}** by *{author}*",
                        color=discord.Color.yellow()
                    )
                    response = await message.reply(embed=embed)
                    await delete_after_delay(response, 30)
                    continue
                
                # Create a button to open the metadata modal
                class UploadButton(discord.ui.View):
                    def __init__(self, file_info):
                        print(f"[DEBUG] Creating upload button for: {file_info['filename']}")
                        super().__init__(timeout=3600)  # 1 hour timeout
                        self.file_info = file_info
                    
                    @discord.ui.button(
                        # Keep the label short - Discord has a 45-character limit
                        label="Add PDF Metadata", 
                        style=discord.ButtonStyle.primary
                    )
                    async def metadata_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                        print(f"[DEBUG] Button clicked by user: {interaction.user.id}")
                        if interaction.user.id != message.author.id:
                            print(f"[DEBUG] Unauthorized user tried to add metadata: {interaction.user.id}")
                            await interaction.response.send_message("Only the uploader can add metadata.", ephemeral=True)
                            return
                        
                        try:
                            # Open the modal form
                            print(f"[DEBUG] Creating modal for user: {interaction.user}")
                            modal = PDFMetadataModal(
                                self.file_info, 
                                ALLOWED_CATEGORIES, 
                                CATEGORY_SUBCATEGORIES, 
                                ALLOWED_LANGUAGES
                            )
                            print(f"[DEBUG] Sending modal to user")
                            await interaction.response.send_modal(modal)
                            print(f"[DEBUG] Modal sent successfully")
                        except Exception as e:
                            print(f"[ERROR] Error sending modal: {e}")
                            print(traceback.format_exc())
                            await interaction.response.send_message(
                                f"An error occurred: {str(e)}", 
                                ephemeral=True
                            )
                
                print(f"[DEBUG] Sending upload button message")
                filename_display = attachment.filename
                if len(filename_display) > 30:
                    filename_display = filename_display[:27] + "..."
                    
                await message.reply(
                    f"📄 Please add metadata for: **{filename_display}**", 
                    view=UploadButton(file_info)
                )
                print(f"[DEBUG] Upload button message sent")
            
            except Exception as e:
                print(f"[ERROR] Error processing attachment: {e}")
                print(traceback.format_exc())
                await message.reply(f"Error processing your PDF: {str(e)}")

        # Delete the category guide after 2 minutes
        await delete_after_delay(category_guide, 120)

async def setup(bot):
    print(f"[DEBUG] Setting up PDFUpload cog")
    await bot.add_cog(PDFUpload(bot))
    print(f"[DEBUG] PDFUpload cog setup complete")